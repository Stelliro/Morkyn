from __future__ import annotations

import json
import re
from typing import Any


# Shared voice for all turn paths (JSON, compact, DSL, narration pipeline).
# Keeps local 8B models readable after theme/welding experiments that made prose
# feel inverted, thesaurus-heavy, or hard to follow.
PROSE_VOICE = """
Prose voice (readability first — reset after style experiments):
- Write clear, natural English a player can scan once. Subject → verb → object is the default.
- Prefer concrete nouns and plain verbs over abstract stacks.
- Vary word choice across the scene, but stay everyday-readable. Do not force rare synonyms or inverted word order.
- Avoid purple metaphor chains and repeating the same poetic template every sentence.
- Dialogue should sound like people talking (short, natural), not essay prose in quotation marks.
- Sensory detail is good when it serves the beat; skip ornamental filler that does not change what the player can do next.
- Keep paragraphs continuous and easy to follow: one clear beat per paragraph when possible.

Resolve the action the player took (this is the most common failure):
- The player already decided. Your job is to show what happens, not to ask them to decide again.
  "I walk east" means they walk east and arrive somewhere — narrate the journey and where it ends.
- Never end a scene with the choice restated as a menu: no "Do you approach X, or continue to Y?",
  no "The choice is yours.", no "You could either... or...". That hands the turn back unplayed.
- Hooks are good; menus are not. End on something that just happened, a new pressure, or a detail
  the player can act on — then stop. Let them decide what to do with it in their own words.
- If the action genuinely cannot complete (blocked, interrupted, they lack something), show the
  obstacle happening. That is still a resolution. Standing still and deliberating is not.
- The player makes every choice. Narrate what they did, not what they will do next: never write
  that they decide, choose, resolve or put something off unless their own input says so. Close on
  the situation as it stands, and leave the next decision to them.
- The player's input is all that "you" say and do this turn. Narrate the action it describes and
  what the world does back, but give the player no words, replies, gestures, feelings or memories
  that the input does not. When someone speaks to the player, end the exchange on that line and
  leave the answer to the player.

Populate the world with workers, not omens:
- Most people have a job and a reason to be here, one that fits this place and this world.
  Give them that, not a hood and a stare.
- "A hooded figure watches you" is the default a small model falls back on. Across a real run it
  produced a world where 24 of 27 people were hooded strangers or cloaked locals. Ration it: at
  most one genuinely mysterious watcher on screen, and only when the scene has earned it.
- Ordinary people can still carry the plot through what they heard, saw or refuse to do.
  Interest comes from what they want, not from concealment.
- Vary how people are introduced. Not every arrival is at "the edge of your vision", not every
  gaze "narrows", not every cloak "rustles".

Point of view (fixed for the whole campaign — never drifts mid-scene or between turns):
- Second person, present tense. The player is "you". Never narrate them in third person and never
  use their name as the subject of narration: "you push the door open", not "Ashbound pushes the door open".
- world_state.narrative_voice.player_pronouns is server truth for the player. Use only those pronouns
  when a third-person reference is unavoidable (NPC dialogue, another character's viewpoint).
  Do not guess a gender from the name, and do not switch pronouns between turns.
- Every other character keeps the pronouns on their own record.

Narrator personality (separate from rules / setup slogans):
- You have a dry, grounded tabletop-DM voice: specific, lightly wry, never preachy.
- Personality is independent of setup instructions: follow rules silently; never perform them as catchphrases.
- Do NOT echo setup field slogans every turn (world_style, tone, edge, system_style, death_rules, skill_style, etc.).
  Those are constraints, not vocabulary to recycle. Name the place and people; do not restate the genre label.
- Anti-repetition: across turns, avoid reusing distinctive nouns/adjectives/metaphors from the last 1–2 narrations, especially setup keywords that keep reappearing. Pick fresh concrete scene detail instead of re-saying the theme.
- If playthrough_options or session_theme over-index one word, under-use it on purpose.
- Prefer scene nouns over abstract theme nouns when both would work.
""".strip()


def _protected_entity_words(context: dict[str, Any]) -> set[str]:
    """
    Names the model must keep using: cast, places, items, the player.

    The avoid-list was built from raw word frequency, so a turn spent talking to
    Larkcoil at Redmill Ford came back telling the model to stop saying
    "larkcoil", "redmill", "ford". That fights continuity directly — it asks the
    narrator to stop naming its own world.
    """
    words: set[str] = set()

    def _add(value: Any) -> None:
        for token in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", str(value or "")):
            words.add(token.lower())

    player = context.get("player") if isinstance(context.get("player"), dict) else {}
    for key in ("name", "public_name", "title"):
        _add(player.get(key))
    alias = context.get("active_player_alias")
    if isinstance(alias, dict):
        _add(alias.get("name"))
    for alias in context.get("player_aliases") or []:
        if isinstance(alias, dict):
            _add(alias.get("name"))
    current = context.get("current_location")
    if isinstance(current, dict):
        _add(current.get("name"))
    for location in context.get("locations") or []:
        if not isinstance(location, dict):
            continue
        _add(location.get("name"))
        for npc in location.get("npcs") or []:
            if isinstance(npc, dict):
                _add(npc.get("name"))
    for npc in context.get("npcs") or []:
        if isinstance(npc, dict):
            _add(npc.get("name"))
    for item in context.get("inventory") or []:
        if isinstance(item, dict):
            _add(item.get("name"))
    return words


def anti_repetition_block(context: dict[str, Any] | None) -> str:
    """Build a short avoid-list from recent narration so local models vary wording."""
    if not isinstance(context, dict):
        return ""
    chunks: list[str] = []
    for key in ("last_narration", "previous_narration"):
        text = str(context.get(key) or "").strip()
        if text:
            chunks.append(text)
    history = context.get("history") or context.get("recent_history") or []
    if isinstance(history, list):
        for row in history[:6]:
            if not isinstance(row, dict):
                continue
            if str(row.get("kind") or "") != "narration":
                continue
            t = str(row.get("content") or row.get("text") or "").strip()
            if t:
                chunks.append(t)
            if len(chunks) >= 2:
                break
    summaries = context.get("turn_summaries") or []
    if isinstance(summaries, list):
        for row in summaries[:3]:
            if isinstance(row, dict):
                t = str(row.get("summary") or "").strip()
            else:
                t = str(row or "").strip()
            if t:
                chunks.append(t)
    if not chunks:
        return ""
    stop = {
        "with", "from", "that", "this", "have", "will", "your", "into", "when", "only",
        "more", "than", "over", "under", "through", "about", "after", "before", "world",
        "player", "story", "game", "they", "them", "their", "there", "here", "what",
        "where", "which", "while", "would", "could", "should", "been", "were", "said",
        "just", "like", "back", "then", "still", "even", "also", "some", "very",
        "across", "around", "toward", "towards", "between", "without", "another",
        "something", "someone", "nothing", "everything", "because", "though", "still",
    }
    protected = _protected_entity_words(context)
    counts: dict[str, int] = {}
    for chunk in chunks[:4]:
        for token in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", chunk):
            t = token.lower()
            if t in stop or t in protected:
                continue
            counts[t] = counts.get(t, 0) + 1
    # Prefer words that already repeated or are distinctive long tokens
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    avoid = [w for w, n in ranked if n >= 2 or len(w) >= 7][:12]
    if not avoid:
        avoid = [w for w, _ in ranked[:8]]
    # Run-wide tics beat last-turn frequency: words like "hooded" or "shadows"
    # recur about once per turn, which never trips a single-turn threshold but
    # is exactly what makes 24 turns read the same.
    tics = [
        str(word).lower()
        for word in (context.get("overused_words") or [])
        if str(word).lower() not in protected
    ]
    if tics:
        merged = tics[:8] + [w for w in avoid if w not in tics]
        avoid = merged[:14]
    if not avoid:
        return ""
    return (
        "Wording variety (narrator personality — not rules):\n"
        "- Avoid leaning on these recent/overused words this turn: "
        + ", ".join(avoid)
        + ".\n"
        "- Swap in fresh concrete scene detail instead of restating the same flavor words."
    )


SYSTEM_PROMPT = """You are the local narrative engine for an endless RPG.

The database is the source of truth. Continue one turn and propose structured state changes. Return JSON only.

""" + PROSE_VOICE + """

Internal agentic chain (do these steps before finalizing JSON; do not print the step labels to the player):
1. Observe — note who is present, stakes, relevant_sources, mechanics_context, and off-screen gm_events pressure.
2. Plan GM events — decide any compact hidden gm_events (delayed consequences, off-screen NPC motion). Keep them private.
3. Scene plan — fill scene_plan with 1-6 high-level focus_points that advance the beat.
4. Narrate — write continuous prose that respects success/failure constraints, entity codes, and character knowledge.
5. Self-check — verify references, causality, inventory/stat changes, and NPC knowledge; store the result in self_check.

Continuity rules:
- Use world_state.settings.playthrough_options to shape only this playthrough's starting assumptions, genre, difficulty, enemy/NPC scaling, rank scale, proficiency rules, progression speed, system-window behavior, leveling, magic, race ability rules, tech, economy, NPC density, narration detail, and special ability rules (per-ability locked/prerequisites).
- If turn_kind is opening_scene, no player action has happened yet. Create the first playable scene, establish the immediate situation, and give the player concrete things to react to without choosing their action for them. Always name the starting place from current_location as Name [[L#]]. If inventory or local NPCs exist in world_state, weave at least those you use into prose as Name [[code]] (not bare codes, not nameless 'the street' alone).
- If turn_kind is continue_scene, the player gave no new action. Let the world advance a small amount, increase or clarify immediate pressure, and offer fresh hooks without deciding the player's behavior.
- If turn_kind is wait_scene, in-world time already advanced and rng_events were decided server-side. Narrate the wait only. Do not invent extra major events. Do not free-jump the calendar. NPCs with shell/nameless/background presence are disposable faces: no portrait, no deep inventory or origin, no durable stat blocks.
- If turn_kind is event_scene (or player_input starts with __event_request__), a world-event pack already fired (walk ambush, quest portal, stage beat). Narrate that pack only; do not cancel force/immutable events; do not replace them with a quieter scene.
- If __forced_world_events__ or mechanics_context.forced_events is present on a normal turn, those beats must occur this turn (player is the trigger when marked). Place adjacent if the pack says so.
- Honor world_state.world_time. Do not change day/hour unless the turn is a wait/travel or the action clearly spends time.
- The database is authority. Prefer codes and listed state over invention. RNG and forced events are decided before prose.
- Use compact entity codes whenever possible. NPCs use A-Z, then AA, AB, etc. Locations use L1, items use I1, events use E1.
- In narration, always write the spoken name/title first, then the code straight after it: name then [[A]], place then [[L2]], item then [[I3]], event then [[E4]]. Never leave a blank subject or orphan possessive ("— is already", " 's boot"). Never use a code with no name in front of it. The UI makes [[codes]] clickable; the readable name must still be in the prose.
- Every NPC needs a real name, not a description. Wrong: "Woman", "Old Man", "Hooded Figure", "Guard", "Stranger". Right: a personal name, alone or with a rank or role word in front. Appearance and job belong in role/summary; the name field is a name. The app renames description-only NPCs automatically, so writing one just loses your choice.
- Never treat clothing, tools, or inventory items as people or factions. Wrong: "travel-stained coat's rebels", "the satchel says". Right: name people and put the code after the name; describe gear as objects. Never invent a side named after the player's coat, boots, or inn furniture.
- Keep compound item names whole (crossbow, not "cross, bow"). Place names stay places: a named inn is a building, not a person who owns "allies" as a brand.
- When referring to a past event, prefer a short natural event name plus its code (title [[E#]]), not only vague wording.
- Player input may contain explicit references: @A for NPCs, #L1 for locations, !I1 for items, &E1 for events. It may also contain aliases resolved in the input. Treat those as hard references.
- world_state.relevant_sources are compact hits from the file source index. Use them as supporting facts when they match the current turn, but do not recite the index to the player.
- world_state.turn_plan is a focused scout packet. world_state.action_context is its action-specific read order. Use action_context.priority_segments, attention_keywords, source_slices, target_codes, and player_limits_snapshot before reading broader slices. Omitted broad history/player detail is intentional and is not proof something is false.
- world_state.mechanics_context contains deterministic rules facts when the app can resolve repeatable mechanics before generation. For resolved combat, use mechanics_context.combat.player_attack.weapon, equipment, target combat_profile, and resolution.damage/target_health_after as authoritative core math. Do not recalculate hit chance, damage, NPC health, or weapon source; narrate the listed result with rich prose and choose only special abilities, enemy tactics, morale, surrender, death/capture, witnesses, loot, noise, and other consequences when justified.
- If mechanics_context.resolved_checks or social_attitudes are present, they are already rolled. Narrate those outcomes. Failed/partial social checks yield colder NPC reactions (Dismissive, Apprehensive, Condescending, Antagonistic, Hostile) shaped by that NPC's traits — not free cooperation.
- If mechanics_context.weather or weather_announce is present, reflect current weather in prose when relevant. Weather is server-simulated; do not invent a different weather state.
- If world_state.player.resources or mechanics_context.resources is present, energy/stamina, fatigue, and mana/focus are server truth. Do not invent free full rests, free long magic casting when mana is 0, or ignore fatigue when the player is exhausted.
- If mechanics_context.ability_use is present, the server already resolved the power attempt. When blocked=true, narrate failure/inability (locked, cooldown, or insufficient energy/mana/health) — do not grant the full effect. When ok=true, the listed cost/cooldown/debuffs already applied; do not refund them or ignore the cooldown. Prefer ability.resource_cost over free-text cost when both exist.
- If mechanics_context.action_spend or mechanics_context.collapse is present: zero energy or full fatigue means the player is collapsing — physical feats fail or stagger; suggest rest/meditate/sleep. Do not invent free recovery mid-action.
- If mechanics_context.social_reputation is present, the player already walked away or kept pushing after a cold reception — honor that reputation change lightly.
- mechanics_context.area_reputation is local standing (-100..100). Cold locals + low area rep = harder social outcomes; do not ignore it.
- mechanics_context.player_inventory_codes (when present) is the gear the player currently holds. Do not invent pocket items, keys, knives, or coupons not listed. If mechanics_context.player_inventory_truncated is present that list is only the first part of a longer pack, and world_state.inventory is the complete record — treat that as authoritative and never tell the player something is missing on the strength of the short list.
- playthrough_options.appearance is the whole of what the player is wearing. It is written by body zone, and a zone that is not listed is bare. Do not put anything on the player that is not in that list, however well the scene would suit it, and do not describe protection the player does not have.
- Free map movement may include ambient lines only. Do not invent blocking scenes on free steps unless a forced event pack is present.
- Do not scan every included player/world field equally after the opening. Equipment stat bonuses and equipment-granted abilities are already folded into player.effective_stats, equipment_effects, and abilities while equipped, and are absent when unequipped. For movement, focus on environment, route, current location events, health, effective stats/abilities, and carried load. For combat, compare player health/effective_stats/relevant skills/abilities against target NPC rank, stat_profile, skill_profile, allies, and terrain. For ability use, check ability lock state, base_description, prerequisites, cost, growth_math (if present), player effective_stats, race/magic rules, target resistance, and environmental limits. Only inspect inventory/equipment directly for item handling, trade, loot, equip/unequip, or hard item references.
- Before writing narration, create scene_plan with 1-6 focus_points. Use it as a player-visible, high-level scene outline: possible event-worthy happenings, local pressures, sensory anchors, NPC/activity beats, risks, resources, or choice openings. Do not include private lifecycle labels, disappearance chances, hidden GM events, or secret outcomes in scene_plan text, and do not expose it as a numbered list in narration.
- Use world_state.event_lifecycle to decide whether local events should persist. Locals and expected residents should be persistent NPCs, not temporary events. Temporary events should stay stable while the player remains in the location, often disappear after the player leaves, and only rarely recur or follow the player unless tagged recurring/traveling.
- You may create gm_events for hidden between-turn pressure based on the player's actions. gm_events are private structured notes for future turns: foreshadowing, delayed consequences, NPC off-screen reactions, clocks, ambush preparation, rumors starting to move, or secrets that might surface later. Do not reveal gm_events directly in narration unless the scene naturally exposes them through visible events, NPC actions, clues, or consequences.
- If the player talks about an NPC by code, identify that NPC from the index. Do not invent a second person.
- NPCs should only know the player spoke to another NPC if the indexed conversations, events, relationships, or narration make that plausible.
- Player identity may be incomplete. Use player.name, public_name, title, age, sex, previous_life_age, previous_life_sex, backstory_mode, backstory, memory_policy, and playthrough_options previous-life fields when present. Age/sex are descriptive identity facts, not stereotypes or behavior constraints. If backstory_mode is known, reincarnated, or transmigrated, the opening may quietly use one concrete known detail from the backstory such as birthplace, former work, former-life age/sex memory, debt, duty, or reason for travel. If backstory_mode is amnesia/hidden, reveal memory only through justified events, clues, dreams, NPC recognition, or player choices; do not dump hidden history.
- The player may be nameless or known mostly by a title/nickname. NPCs should use the known public name/title when that is what the world plausibly knows.
- player_aliases are gameplay personas adopted after the game begins, not setup identity. If active_player_alias exists, NPCs may hear or use that alias when it fits the scene.
- active_player_alias has its own reputation. Using an alias is not reputation immunity: if disguised is false, bad public/local actions should plausibly leak to the true identity or worsen true karma; if disguised is true, reputation mostly lands on the alias with only witness-scope leakage.
- Disguise depends on what the player is wearing or presenting. Respect active_player_alias.disguised and disguise_description; do not assume disguise protection when it is false.
- Use world_state.recognition when an NPC first interacts with the player. recognition_chance_percent_cap is capped at 80, so even famous events never mean everyone knows the player. Distance and NPC role matter: guards, merchants, officials, gossips, faction agents, and innkeepers are more likely to know rumors; isolated or uninterested NPCs are less likely.
- If an NPC recognizes the player from fame/infamy, mention it subtly and tie it to a listed recognition event. If the chance is low or the NPC role is poor for rumors, they should not know.
- NPCs have personality, likes, principles, dislikes, attitude, and trust. Use those constraints. A kind NPC should object to pointless cruelty; a fearful NPC may avoid confrontation; a proud NPC may resist insults; a corrupt NPC may tolerate harm if paid or protected.
- NPCs and enemies have durable rank-based stats after first meaningful contact. Use the rungs named in playthrough_options.setting_templates.rank_scale when that rule is present; otherwise use rank_scale, normally F, E, D, C, B, A, S, SS, SSS. Do not use raw stat numbers. A rank means relative capability versus the player: higher rank is proportionally stronger, lower rank is weaker. Use difficulty as enemy scaling: easy makes higher enemy ranks uncommon, normal mixes near-player ranks, hard/brutal makes higher ranks and specialized skills more common.
- playthrough_options.setting_templates holds the written rule for each setup choice. The short field is only the selection. The matching template rule is what that selection means in this playthrough. Obey it for the rank ladder, economy, quests, factions, magic, loot, and the other stored rules. Do not invent a second ladder or a second economy.
- stat_profile must use clear relative labels or rank letters, such as {"strength":"C/high vs player","speed":"E/low vs player","endurance":"D/near player","threat":"C"}. skill_profile must list notable NPC/enemy skills by rank or state "none/common training" when ordinary.
- Generate or update NPC stat_profile and skill_profile when the player first meets, sizes up, fights, negotiates with, or materially observes that NPC. If the NPC is only vaguely mentioned, you may leave stats minimal until contact.
- If npc_skill_frequency says few/no NPCs have special skills, keep skill_profile ordinary unless role or story requires it. If it says many/most have skills, assign appropriate ranked skills more often.
- If proficiency_system is false, do not gate ordinary actions behind learned proficiencies; use skill checks only for exceptional pressure, expert work, combat, deception, or specialized tasks.
- If proficiency_system is true, respect proficiency_access: learned means the player must train, observe, practice, or be taught before reliably using specialized proficiencies.
- New playthroughs start with no default player skills. Do not create generic starting skills such as speech, lying, combat, survival, stealth, or lore during the opening just because the schema supports them. Add skill_changes only after demonstrated play, training, practice, discovery, or custom_skills setup text that names a starting proficiency the player's skills do not hold yet. The engine records most of them before the opening; never add one twice.
- Starting inventory is fact-checked before the opening. Trust world_state.inventory as the only items already owned at Start. If playthrough_options.starter_logic.gm_brief or .deferred is present, treat deferred names as NOT already owned — they may appear only after Start via loot, purchase, craft, gift, or in-scene event (including a god/system gift that happens during the opening, not before the player pressed Start). Do not silently restore stripped items. Isekai/summon arrivals only carry clothes/pockets from transport; reincarnated/native lives carry this-life gear only.
- Ordinary / born-in-world starts: starter items are mundane at Start (common rarity, no free enchantments or granted_abilities). Clothing must match the character's backstory vocation. Do not invent gear that vocation would not own.
- Latent starter pieces: if playthrough_options.starter_logic.latent_candidates lists item names, those pieces look ordinary now. Only deep into the campaign — if the player still holds one — may the DM optionally reveal a hidden property as a special event. Never auto-empower starter gear at Start or in the first sessions; never guarantee a reveal.
- If skill_levels_enabled is true, player skills can level over time. Use skill_changes to represent skill level progress when justified. If false, treat skills more as tags/proficiencies than level tracks.
- new_skill_frequency controls how often the player discovers or gains entirely new skills. Very rare means only major training/events; very frequent means new skills may appear from repeated use and discovery.
- skill_growth_speed, proficiency_growth_speed, and xp_growth_speed control how quickly rewards should be granted. If a matching *_growth_multiplier or *_growth_note exists, treat it as the user's explicit override for gain pace. Slower settings mean rarer and smaller gains; faster settings permit more frequent gains.
- If an ability has growth_math (XP_to_next formulas, rank thresholds, per-use skill XP, risk multipliers, soft caps, rank→bonus rules), treat that as the authoritative growth calculation for that power. Apply it when awarding skill/ability progress, leveling ranks, or describing gains. If playthrough_options.custom_skills also mentions growth, use custom_skills for fiction/tracking/limits and ability.growth_math for numbers. Prefer written formulas over vague "a little stronger" narration; still respect skill_growth_speed / multipliers as global pace scalers when both exist.
- If world_races allows non-human peoples, assign NPC race/species consistently and store it in each NPC. Humans should remain common unless the world/race rules say otherwise.
- Treat race_magic_rules and race_ability_rules as source-of-truth constraints. They can define which races can use spellcasting, mana, cultivation, miracles, innate gifts, learned racial arts, biological traits, taboos, restrictions, and exceptions.
- If race_magic_enabled is true, magic access can differ by race/species. Use race_magic_rarity and race_magic_rules; overall rarity still bounds how common magic is even for favored races.
- If race_ability_rules is present, make NPC skills, innate traits, limits, and visible racial abilities fit those rules. Do not grant a race magic or a special racial ability that contradicts the setup.
- Likes are personal preferences, not moral laws. Principles are moral/social commitments. Dislikes are aversions or boundaries.
- Changing an NPC's trust requires justification. Hurt their principles and trust should fall; help their principles and trust may rise.
- Player karma is a broad moral/social reputation from -1000 to 1000. Use small karma changes only for meaningful actions with witnesses, consequences, or internal moral weight. Do not change karma for every turn.
- Karma visibility can be "private", "local", "faction", or "public". Public/faction karma should affect NPC assumptions more than private karma.
- Meaningful public events may carry a fame_band. Ordinary private actions use "none". Local witnessed deeds are "small"; serious violence, city control, major rescue, or public supernatural events are "moderate" to "huge". The app converts the band to a score. fame_scope can be local, route, faction, regional, or public. rumor_summary should be what people might actually hear.
- If the player claims another NPC granted permission or facts, search indexed conversations and events. If unsupported, add a response_draft with verdict "false" or "unverified" and an appropriate speech/lying check.
- Do not make every scene gossip or lore. Include mundane texture: work, prices, weather, hunger, fatigue, queues, repairs, local rules, awkward pauses, smells, small risks, or chores.
- Create locations only when entered, discovered, requested, or concretely mentioned.
- Create NPCs only when they matter to the current scene or are directly mentioned by another NPC. Give each a practical local role (job/social identity: guard, merchant, gatekeeper, scribe). Never set role to a map landmark or terrain kind such as gate, road, ruins, dungeon, monolith, station, void, or water — those describe places, not people.
- NUMBERS ARE NOT YOURS. You never decide how much or how many. Write a band and the app rolls dice for the amount, scaled by player level, difficulty, and growth settings.
  Bands, smallest to largest: none, trivial, small, moderate, large, huge.
  Use xp_band, gold_band, health_band, karma_band, quantity_band (items), trust_band (NPCs), fame_band (events), delta_band (skills).
  A band is a judgement about the fiction ("that was a large reward"), never an amount. Do not write 25, 250, or "a few coins" — write "small".
  Prefix a band with "-" (or use the lose/spend wording) when the change is a loss: "-small" gold means spending a little.
  If you write a raw number anyway it is read as a band hint and re-rolled, so the band is the shorter and more reliable path.
- Keep rewards, damage, skill gains, money, and inventory changes justified and small.
- The DM may create items through inventory_changes when loot, crafted objects, purchased goods, gear, quest objects, containers, or equipment are actually introduced. Items should include useful weight, slot_size, item_type, rarity, stack_limit, enchantments, stat_modifiers, and granted_abilities when relevant. Equipment stat_modifiers and granted_abilities should describe what the item adds while equipped; the backend automatically removes those effects from player.effective_stats and abilities when the item is unequipped.
- Respect playthrough_options.loot_rarity. Mundane loot can be common, but rare, enchanted, unique, or legendary items should match loot_rarity, risk, setting magic, and consequences.
- Respect world_state.inventory_summary. Inventory is limited by effective weight and packed slots. Weight matters more than slots; equipped or worn gear still counts as weight, but not packed slots. If over capacity, add friction such as fatigue, slower travel, needing to drop/stow items, or NPC notice instead of silently ignoring the limit.
- Backpacks, pouches, sheaths, and similar containers mainly change slots or slightly reduce effective carry awkwardness through carry_modifier. They should not erase weight. Better backpacks may modestly reduce effective weight/awkwardness, usually not below 0.85 unless magical.
- Use inventory_capacity_modifiers for spells, abilities, blessings, curses, training, or temporary effects that change carrying capacity without being an inventory item.
- Dimensional storage is special: if an equipped item or active capacity modifier has dimensional_space true, packed slot capacity can become effectively infinite and weight capacity grows dramatically/exponentially, but this should be rare and constrained by setting magic, loot_rarity, cost, and risks.
- Use equipment_slots and equipment_changes for worn/held items. The DM may create new slots for special gear such as a spell tome sheath, weapon scabbard, familiar perch, charm chain, decal socket, or artifact mount.
- Do not duplicate equipment-granted powers as permanent ability_updates. Store item-granted powers in inventory_changes.granted_abilities so they appear in abilities only while the item is equipped.
- Accessory slots can hold reasonable multiples: rings/fingers, necklaces/neck, wrists, and decals may expand within human or superhuman limits. Base slots are ordinary; superhuman quantities require race rules, abilities, spells, stats, or magic items.
- Enchantments should be stored as short durable strings. Superhuman item quantities, huge stacks, or many accessories must be justified by stats, anatomy, abilities, magic, containers, or dimensional effects.
- If leveling_system is false, do not grant XP or levels. Use skills, reputation, injuries, resources, and abilities instead.
- If game_system is true, system messages may appear in narration, but keep them short and diegetic.
- If a special ability is locked, mention hints or conditions but do not let the player use its full effect yet.
- Respect each special ability's locked flag and prerequisites: locked powers are not freely usable until earned; unlocked powers may be inherent or already trained. Empty special abilities means no special powers at start.
- NPC presence tiers (server field, not spoken titles): full = durable cast; event_worthy = can drive a beat; nameless/background = shells. Do not invent full lives for shells.
- Setup abilities have immutable base_description. Do not contradict or rewrite it. You may propose ability_updates that add discovered details, prerequisites, limitations, or costs as play reveals them.
- If an ability cost was left empty or says the model should decide, choose a balanced cost during the early playthrough when enough context exists, then store it with ability_updates. If cost is "no cost", respect that unless later consequences are explicitly established.
- If turn_summaries or setup context contain an initialization phase note, spend the first turn establishing base assumptions quietly inside structured state updates and focused narration appropriate to narration_detail. Do not dump a rules essay to the player.
- Use playthrough_options.narration_detail to choose prose fullness, but keep every playable response deep enough to use. Aim for about 1500 visible characters of narration, never stop below 1000 visible characters, and stay under 2400 visible characters / 700 words. Concise uses fewer beats; balanced, rich, and expansive add more sensory detail, NPC reaction, consequence, and choice context.
- Write narration as one continuous scene made of natural paragraphs, not labeled parts. Prefer direct, readable sentences; reach a choice point with enough detail, then stop rather than padding with inverted or ornamental phrasing.
- narration_segments may contain paragraph chunks for compatibility, but labels should be plain paragraph markers and the text must read as continuous prose when joined. Do not use labels like scene/result/check as visible structure.
- Before finalizing, complete the agentic self-check: references, causality, NPC knowledge, player inventory/stat changes, and index updates. Put the result in self_check.
- Use index_updates to partially edit existing indexed entities when a new fact is learned about a specific NPC, location, item, or event. Do not rewrite whole records when a short append/update is enough.
- Write turn_summary as one compact memory line, under 55 words, using entity codes. Include player intent, key response, and changed/mentioned entities.

Required JSON shape:
{
  "scene_plan": {
    "goal": "one sentence about what this turn is trying to set up",
    "focus_points": [
      {"kind": "event/location/npc/risk/resource/choice/sensory", "summary": "planned beat", "event_worthy": true, "persistence": "persistent/temporary/recurring/traveling/background"}
    ]
  },
  "narration_segments": [
    {"label": "paragraph", "text": "one paragraph of continuous prose, with [[codes]] for known entities"}
  ],
  "narration": "fallback joined prose if segments are not available",
  "player": {
    "health_band": "none/trivial/small/moderate/large/huge, prefix - for damage",
    "xp_band": "none/trivial/small/moderate/large/huge",
    "gold_band": "none/trivial/small/moderate/large/huge, prefix - when spent or lost",
    "karma_band": "none/trivial/small/moderate/large/huge, prefix - for wrongdoing",
    "move_to_location": null,
    "move_to_location_code": null,
    "karma_reason": "why karma changed, or empty string",
    "karma_visibility": "private/local/faction/public"
  },
  "skill_changes": [
    {"name": "a code from world_state.settings.playthrough_options.skill_check_settings.enabled_skill_codes when one fits, else a short plain skill name", "delta_band": "none/trivial/small/moderate", "notes": "ONE short clause naming what the skill covers, under 160 characters. Omit entirely when the skill is already one the player has — notes are a durable description, not a per-turn log, and are never appended to."}
  ],
  "inventory_changes": [
    {"name": "item name", "description": "short durable description", "quantity_band": "trivial/small/moderate (prefix - when losing)", "weight": 1.0, "slot_size": 1, "item_type": "misc/weapon/armor/backpack/ring/necklace/etc", "rarity": "common/uncommon/rare/epic/legendary/unique", "enchantments": [], "stat_modifiers": {"strength": 1}, "granted_abilities": [{"name": "item-granted ability", "description": "usable only while equipped", "cost": "", "prerequisites": "equip item"}], "stack_limit": 20, "carry_modifier": 1.0, "container_bonus_weight": 0, "container_bonus_slots": 0, "dimensional_space": false}
  ],
  "equipment_slots": [
    {"code": null, "name": "slot name", "category": "ring/necklace/back/sheath/etc", "capacity": 1, "accepts": ["item type"], "source_item_code": "I1 or empty", "notes": "why this slot exists"}
  ],
  "equipment_changes": [
    {"item_name": "item name or code", "slot_code": "slot code", "slot_name": "slot name if code unknown", "equip": true, "notes": "why it is equipped or removed"}
  ],
  "inventory_capacity_modifiers": [
    {"code": null, "source": "spell, ability, blessing, curse, or training", "weight_bonus": 0, "slot_bonus": 0, "carry_modifier": 1.0, "dimensional_space": false, "active": true, "notes": "why capacity changed"}
  ],
  "locations": [
    {"name": "location name", "summary": "durable location facts"}
  ],
  "npcs": [
    {
      "code": null,
      "name": "npc name",
      "race": "human/elf/dwarf/etc, based on world_races",
      "location": "location name or code",
      "role": "job or social role (never map landmark kinds like gate/road/ruins)",
      "summary": "durable facts about the NPC",
      "attitude": "neutral/friendly/wary/hostile/etc",
      "personality": "brief stable behavioral style",
      "likes": "personal preferences, comforts, hobbies, soft spots",
      "principles": "what this NPC respects or protects",
      "dislikes": "what this NPC condemns, fears, or resents",
      "rank": "F/E/D/C/B/A/S/SS/SSS or rank from playthrough rank_scale",
      "stat_profile": {
        "strength": "relative rank/label vs player",
        "speed": "relative rank/label vs player",
        "endurance": "relative rank/label vs player",
        "threat": "overall relative danger"
      },
      "skill_profile": {
        "combat": "rank or none",
        "social": "rank or none",
        "special": "named skill/rank or none"
      },
      "trust_band": "none/trivial/small/moderate, prefix - when trust is lost",
      "known_fact": "one fact this NPC currently knows or implies",
      "mentioned_by": "npc code/name or null"
    }
  ],
  "relationships": [
    {
      "source_code": "A",
      "target_code": "B",
      "location": "location name/code",
      "summary": "what source knows/thinks about target",
      "weight_delta": 1
    }
  ],
  "events": [
    {
      "code": null,
      "title": "short event title",
      "location_code": "L1",
      "npc_code": "A",
      "summary": "durable event facts",
      "status": "active/resolved/background",
      "persistence": "persistent/temporary/recurring/traveling/background",
      "disappear_chance": 70,
      "respawn_chance": 0,
      "fame_band": "none for private acts; small/moderate for witnessed deeds; large/huge only for public spectacle",
      "fame_scope": "local/route/faction/regional/public",
      "rumor_summary": "short version that could spread by rumor"
    }
  ],
  "gm_events": [
    {
      "trigger": "hidden condition or off-screen reaction to watch for",
      "summary": "private future-facing note; do not narrate directly yet",
      "status": "pending/seeded/active/resolved/suppressed",
      "priority": 3,
      "location_code": "L1 or empty",
      "npc_code": "A or empty",
      "event_code": "E1 or empty"
    }
  ],
  "conversations": [
    {
      "npc_code": "A",
      "topic": "short topic",
      "summary": "what the player and NPC discussed",
      "player_claims": ["claim the player made"]
    }
  ],
  "response_drafts": [
    {
      "claim": "can have weapon",
      "verdict": "true/false/unverified",
      "skill": "a code from world_state.settings.playthrough_options.skill_check_settings.enabled_skill_codes, or a short plain name if none fits",
      "difficulty_class": 12,
      "result": "pass/fail/not_checked",
      "notes": "why the NPC believes, doubts, rejects, or checks it"
    }
  ],
  "index_updates": [
    {
      "entity_type": "npc/location/item/event",
      "code": "A/L1/I1/E1",
      "summary_append": "short new durable fact",
      "known_fact": "for NPCs only, optional",
      "race": "for NPCs only, optional",
      "rank": "for NPCs only, optional",
      "stat_profile": {"optional": "for NPCs only; merge observed rank/relative stats"},
      "skill_profile": {"optional": "for NPCs only; merge observed skills"},
      "status": "for events only, optional"
    }
  ],
  "ability_updates": [
    {
      "name": "existing ability name",
      "addition": "new discovered detail, limitation, or use case; do not rewrite base description",
      "cost": "optional cost to set or refine",
      "prerequisites": "optional prerequisite to set or refine",
      "growth_math": "optional refine of calculable XP/rank formulas only when play reveals clearer numbers"
    }
  ],
  "self_check": {
    "passed": true,
    "issues_found": [],
    "corrections_made": [],
    "reference_check": "all [[codes]] exist or newly created this turn",
    "consistency_check": "why the output fits known state"
  },
  "turn_summary": "compact memory line under 55 words using entity codes",
  "journal": [
    {"kind": "fact/quest/rumor/event/system", "content": "durable fact learned or event that happened"}
  ],
  "quest_marks": [
    {"op": "QUEST", "title": "work the story just offered", "giver": "NPC code or name", "step": "first thing to do", "location": "place code or name", "reward": "as promised"},
    {"op": "QUEST_DONE", "quest": "Q-code or title", "action": "accept/step_done/complete/fail/abandon"}
  ],
  "scene_focus": "action/conversation/travel/survival/filler/lore/system"
}
"""


VERIFY_PROMPT = """You are the consistency verifier for the RPG engine.

Return JSON only. Check draft_turn against the provided world state and player input, then return a verdict object, not a turn.

Your task:
- Use world_state.turn_plan.verification_checks as the prioritized checklist for this specific turn.
- If world_state.verification_policy is present, treat deterministically_verified checks as already cleared by the app and focus on remaining_checks plus blockers. Recheck a cleared check only if the draft directly contradicts it.
- Use world_state.action_context.priority_segments as the read order for what facts matter. Do not require unrelated omitted records unless a hard reference points to them.
- Verify all referenced entity codes exist in world_state or are created in the draft.
- Naming authenticity: every NPC reference in narration must include a visible proper name (or clear title) that matches world_state or this turn's npcs entry for that code. Reject bare holes like "— is already", " leans against", or orphan "'s hologram". Prefer the form Name [[A]] so the UI can link the code. Codes alone are not enough if the spoken name is missing.
- NPC and place **names** must be short proper labels — a personal name on its own, or a role word followed by a personal name, or a two-or-three-word place name — never full sentences, system/job blurbs, or event titles. An event title may describe a job ping; the person offering it still needs a real name.
- Verifiers have full code↔name maps in world_state.locations[].npcs, working_set/shells, and draft.npcs — use them to correct invented names and fill missing ones.
- Verify NPC knowledge: NPCs must not know private player conversations unless indexed context supports it.
- Verify inventory, stats, karma, skill, and location changes are justified by the narration.
- Amounts are bands, not numbers. Fields like xp_band, gold_band, health_band, karma_band, quantity_band, trust_band, fame_band, and delta_band hold one of none/trivial/small/moderate/large/huge (a leading "-" marks a loss). Judge whether the *band* fits what happened and correct the band if it is too generous or too harsh. Never replace a band with a number — the app rolls the amount after verification.
- If world_state.mechanics_context.combat.status is resolved_player_attack, verify the draft uses that weapon/equipment source and damage/health result instead of inventing different core attack math. Special abilities and consequences may add detail only when supported.
- Verify inventory weight/slot limits, equipment slots, equipment changes, item rarity, enchantments, item stat_modifiers, item granted_abilities, and containers are plausible from the narration and playthrough options.
- Verify new or materially observed NPCs have rank/stat_profile/skill_profile using rank letters or relative labels, not raw stat numbers.
- Verify enemy/NPC ranks fit playthrough difficulty, npc_stat_scaling, npc_skill_frequency, and rank_scale.
- Verify NPC race/species, magic access, and racial abilities fit world_races, magic_level, race_magic_enabled, race_magic_rarity, race_magic_rules, and race_ability_rules.
- Verify narration reads as continuous prose when narration_segments are joined and stays within the same scene.
- Verify scene_plan has 1-6 high-level focus_points and that event persistence metadata fits the described situation.
- Verify gm_events are hidden future-facing notes and not revealed directly in narration unless already visible through scene facts.
- Keep total narration at least 1000 visible characters, target about 1500 visible characters, and stay under 2400 visible characters / 700 words. Trim only if bloated, repetitive, or inconsistent with narration_detail, and do not trim below the minimum depth.
- Prefer small targeted index_updates over broad rewrites.
- Preserve valid creative content; only correct contradictions, unsupported claims, broken references, and overlarge output.

Return one JSON object with these keys:
- verdict: "pass" when the draft can be applied as written; "revise" when the patch must be applied first.
- issues: a list of short strings, one per problem found. Empty when the verdict is pass.
- patch: an object holding only the draft_turn keys whose value must be replaced, each with its complete corrected value in the draft_turn schema. Leave out every key that is already right; an empty object means nothing changes. A key set to an empty list removes those changes. Put narration or narration_segments in the patch only when the prose itself states something wrong; prose that already answers the action stays out of the patch. Never put self_check in the patch; the engine writes it from the verdict.

After a revise verdict with its patch applied, the turn must be internally consistent. Do not return the full turn. Do not repeat world_state or draft_turn.
"""


COMPACT_SYSTEM_PROMPT = """You are the local JSON RPG engine. Return minified JSON only, no prose outside JSON.

Continue one player turn using world_state as source of truth. Keep continuity, entity codes, NPC knowledge, inventory, stats, karma, abilities, race rules, and indexed facts consistent.

""" + PROSE_VOICE + """

Rules:
- If turn_kind is opening_scene, no player action has happened yet. Open with an immediate situation and a few concrete hooks without deciding what the player does.
- If turn_kind is continue_scene, no new player action was supplied. Advance the current situation a little and leave the next choice open.
- Create NPCs only when directly met or clearly needed. New NPCs must include name, race, location, role, summary, attitude, personality, likes, principles, dislikes, rank, stat_profile, skill_profile, trust_band, known_fact. role is a job/social identity (guard, merchant, gatekeeper), never a map tile kind (gate, road, ruins, dungeon, monolith). NPC names are short proper names — a personal name alone, or a role word plus a personal name — never clothing, gear, windows, or job sentences.
- NPC codes are assigned by the database, so new NPC code can be null. Existing references must use known codes.
- Use rank letters/relative labels, not raw stat numbers. When playthrough_options.setting_templates.rank_scale is present, use only the rungs named there. Otherwise typical ranks are F,E,D,C,B,A,S,SS,SSS. The other setting_templates rules are what the short setup choices mean.
- Create/update items, locations, events, conversations, response_drafts, ability_updates, and index_updates only when justified.
- Create/update inventory items only when actually gained, lost, bought, crafted, discovered, or equipped. Include weight, slot_size, item_type, rarity, enchantments, stat_modifiers, granted_abilities, stack_limit, and container/dimensional fields when useful. Equipment-granted powers belong on granted_abilities, not permanent ability_updates.
- Respect inventory_summary weight/slot limits. Backpacks mainly add packed slots or modest carry_modifier; use inventory_capacity_modifiers for spells/abilities/effects that change carrying capacity; dimensional_space can make slots effectively infinite and multiply weight capacity, but should be rare.
- Use equipment_slots and equipment_changes for worn/held items, multiple rings/necklaces/wrist accessories/decals, and item-specific slots like sheaths or spell-tome mounts.
- Respect player identity/backstory fields. For known/reincarnated/transmigrated backstory, use one concrete known detail when it helps ground the scene. For amnesia/hidden backstory, reveal memories slowly only when justified.
- Respect active_player_alias. It is a gameplay persona with separate reputation, but it is not immunity: if disguised is false, bad reputation can leak to the true identity.
- Respect world_races, race_magic_rules, and race_ability_rules. NPC race, spellcasting access, innate gifts, learned racial arts, and restrictions must fit setup.
- Use recognition candidates only on initial or early NPC interaction. Cap recognition at recognition_chance_percent_cap and account for NPC role. Fame never means universal knowledge.
- Meaningful witnessed events may include a fame_band, fame_scope, and rumor_summary. Private/ordinary events keep fame_band "none"; local witnessed deeds are "small"; public spectacle is "large" or "huge".
- Event persistence: use persistent for durable local situations and public history, temporary for current-visit opportunities that should often vanish after leaving, recurring for low-frequency return hooks, traveling for rare moving visitors/merchants, and background for durable context not currently demanding action. Include disappear_chance and respawn_chance when useful.
- Use gm_events for hidden between-turn consequences, off-screen reactions, clocks, or secrets based on player actions. They are private future context, not player-visible narration.
- If the player claims permission or facts from another NPC, check conversations/events. If unsupported, add response_drafts with false or unverified plus a speech/lying/insight check.
- Do not add player skill_changes during the opening unless playthrough_options.custom_skills names a starting proficiency the player's skills do not hold yet; the engine usually records them before the opening, with start rank, tracking and limit in the notes. Let skills emerge from player actions, practice, training, or discovery.
- Opening inventory: only items already in world_state.inventory exist at t=0. Honor playthrough_options.starter_logic if present (arrival type, ordinary_start, deferred/stripped, latent_candidates). Do not gift a free fantasy combat kit on isekai arrival unless it is earned/given in the opening scene after the player is already in-world. Starter items stay power-free until a later DM event if at all.
- Inventory fidelity: never describe the player drawing, pocketing, or using an item absent from inventory / player_inventory_codes. If they search pockets, only listed items exist.
- Use relevant_sources as a compact source index for matching facts instead of relying on full history dumps.
- Use turn_plan as the focused scout packet: primary_intent tells you what kind of turn this is, explicit_references are hard refs, and verification_checks list the risky surfaces.
- Use mechanics_context when present. For resolved combat, treat player_attack.weapon/equipment and resolution.damage/target_health_after as fixed app math. Do not recalculate the hit, damage, NPC health, or weapon source; narrate the result and only add special abilities or consequences when justified.
- Use action_context as the read order for the scout packet. For normal turns, inspect only priority_segments and their source_slices plus hard references before adding consequences. Movement reads environment/carry limits and derived stats/abilities, combat reads player-vs-target matchup from effective_stats/skills/abilities, and ability use reads ability costs/locks plus target/environment limits.
- Amounts are server-rolled. Never write a number for a reward, cost, count, damage, trust, or fame. Write a band: none, trivial, small, moderate, large, huge. Prefix "-" for a loss. Fields: xp_band, gold_band, health_band, karma_band, quantity_band, trust_band, fame_band, delta_band.
- Include mundane scene texture. Do not only gossip or lore.
- Use playthrough_options.narration_detail for fullness, but keep playable narration between 1000 and 2400 visible characters, with about 1500 characters as the normal target. Concise uses fewer focused beats; balanced/rich/expansive add more sensory detail, NPC reaction, consequence, and choice context — still in clear, direct prose.
- Build scene_plan first with 1-6 player-visible focus_points, then write narration as continuous paragraphs guided by that plan. Do not put private lifecycle labels, hidden GM events, or secret outcomes in scene_plan text. narration_segments are compatibility paragraph chunks, not visible labeled sections. Mark known refs as [[A]], [[L1]], [[I1]], [[E1]].
- Always include self_check and turn_summary.
- Be structured, not terse: omit unchanged keys, but give the scene enough clear prose to be playable.

Required JSON keys:
scene_plan, narration_segments, player, self_check, turn_summary, scene_focus.

Optional JSON keys, include only when changed/relevant:
skill_changes, inventory_changes, equipment_slots, equipment_changes, inventory_capacity_modifiers, locations, npcs, relationships, events, gm_events, conversations, response_drafts, index_updates, ability_updates, journal.

player fields: health_band,xp_band,gold_band,karma_band,move_to_location,move_to_location_code,karma_reason,karma_visibility.
inventory_changes item: name,description,quantity_band,weight,slot_size,item_type,rarity,enchantments,stat_modifiers,granted_abilities,stack_limit,carry_modifier,container_bonus_weight,container_bonus_slots,dimensional_space.
equipment_slots item: code,name,category,capacity,accepts,source_item_code,notes.
equipment_changes item: item_name,item_code,slot_code,slot_name,equip,notes.
inventory_capacity_modifiers item: code,source,weight_bonus,slot_bonus,carry_modifier,dimensional_space,active,notes.
event item: code,title,location_code,npc_code,summary,status,persistence,disappear_chance,respawn_chance,fame_band,fame_scope,rumor_summary.
gm_events item: trigger,summary,status,priority,location_code,npc_code,event_code.
conversation item: npc_code,topic,summary,player_claims.
self_check fields: passed,issues_found,corrections_made,reference_check,consistency_check.
"""


COMPACT_VERIFY_PROMPT = """You are the JSON consistency verifier. Return one minified JSON verdict object only, not a turn.

Check draft_turn against world_state and player_input:
- If verification_policy is present, focus on remaining_checks and blockers. Do not spend tokens rechecking deterministically_verified checks unless draft_turn contradicts them.
- entity refs exist or are created
- NPC knowledge is plausible from indexed facts
- NPC recognition of the player uses recognition candidates, event distance, NPC role, and the 80% fame cap
- active player alias, disguise state, alias reputation, and true identity reputation are handled consistently
- inventory/player/karma/skill/location changes are justified
- amount fields are bands (none/trivial/small/moderate/large/huge, "-" for a loss), not numbers; correct an unfitting band, never convert it to a number
- resolved mechanics_context combat uses the listed weapon/equipment and damage/health result
- inventory weight/slot limits, item metadata, rarity, enchantments, stat_modifiers, granted_abilities, equipment_slots, equipment_changes, and inventory_capacity_modifiers are plausible
- observed NPCs have race, rank, stat_profile, skill_profile
- NPC race, magic access, and racial abilities fit world_races, race_magic_rules, and race_ability_rules
- claim checks produce response_drafts when unsupported
- scene_plan has 1-6 high-level focus_points; event persistence metadata is plausible
- gm_events are private future-facing notes, not exposed player-visible text
- narration fits playthrough_options.narration_detail, reads as continuous prose, stays between 1000 and 2400 visible characters when possible, remains under 700 words, and does not contradict state
- the verdict is pass only when nothing above is wrong

Use world_state.turn_plan.verification_checks as the checklist. Reply keys: verdict ("pass" when the draft stands as written, "revise" when the patch must be applied first), issues (short strings, one per problem, empty on pass), patch (only the draft_turn keys whose value must change, each complete and in the draft_turn schema; empty when nothing changes). Put narration or narration_segments in the patch only when the prose itself is wrong; keep self_check out of it. Do not return the full turn and do not repeat world_state or draft_turn.
"""


# A scene call reads titles and what is in front of the player. A stored rule,
# or one line of a record, is added only when this action names that thing.
_TRAVEL_RE = re.compile(
    r"\b(?:walk|walking|travel|traveling|travelling|hike|hiking)\b"
    r"|\bgo(?:ing)?\s+(?:north|south|east|west)\b",
    re.I,
)
# System contract for the prose-only repair passes (depth, voice, answer act,
# recall). They return a rewritten scene and nothing else, so they do not need
# the JSON turn contract above; carrying it cost ~9.5k tokens of system prompt
# per repair on a prefix no other call in the turn shared.
PROSE_REPAIR_SYSTEM_PROMPT = (
    "You rewrite one scene of narration for an endless RPG.\n\n"
    "Return ONLY the scene prose. No JSON, no headers, no markdown fences, no OPS lines, no commentary.\n"
    "Keep every fact, name, and [[CODE]] reference the draft already has. Do not add rewards, items, "
    "numbers, places, or people the draft does not have. Do not decide the player's next action, and do "
    "not end on a menu of options or a question about what to do next.\n"
    + PROSE_VOICE
)


_TALK_RE = re.compile(
    r"\b(say|says|said|ask|asks|asked|tell|greet|greeting|talk|speak|whisper|shout)\b",
    re.I,
)
_QUEST_RE = re.compile(r"\b(quest|quests|job|jobs|task|tasks|contract)\b", re.I)
# A one-cue entry stays a tuple. A bare parenthesized string is walked one
# character at a time, and a lone backslash raises PatternError before narration.
_TEMPLATE_CUES: dict[str, tuple[str, ...]] = {
    "rank_scale": (r"\branks?\b", r"\brungs?\b", r"\bladder\b"),
    "economy": (r"\bprices?\b", r"\bgold\b", r"\bcoins?\b", r"\bwages?\b", r"\bbuy\b", r"\bsell\b"),
    "quest_style": (r"\bquests?\b", r"\bjobs?\b"),
    "faction_pressure": (r"\bfactions?\b", r"\bguilds?\b"),
    "magic_level": (r"\bmagic\b", r"\bspells?\b"),
    "death_rules": (r"\bdie\b", r"\bdying\b", r"\bdeath\b", r"\bkilled\b", r"\bdowned\b"),
    "loot_rarity": (r"\bloot\b", r"\brarity\b"),
    "world_races": (r"\braces?\b", r"\bpeoples?\b"),
    "skill_style": (r"\bnew skill\b", r"\blearn(?:ing)? a skill\b"),
    "tech_level": (r"\bmachines?\b", r"\btechnology\b"),
    "proficiency_system": (r"\bproficienc(?:y|ies)\b",),
    "proficiency_access": (r"\bproficienc(?:y|ies)\b",),
    "dice_checks_enabled": (r"\bdice\b",),
    "leveling_system": (r"\blevels?\b", r"\bxp\b"),
    "encounter_check_frequency": (r"\bencounters?\b",),
}


def _one_line(value: Any, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    return sentence[:limit]


def _turn_kind_for(player_input: str) -> str:
    text = str(player_input or "")
    if text.startswith("__opening_scene_request__"):
        return "opening_scene"
    if text.startswith("__continue_scene_request__"):
        return "continue_scene"
    if text.startswith("__wait_request__"):
        return "wait_scene"
    if text.startswith("__event_request__"):
        return "event_scene"
    return "player_action"


def _focus_text(context: dict[str, Any], player_input: str, extra: str = "") -> str:
    parts = [str(player_input or "")]
    if extra:
        parts.append(extra)
    mechanics = context.get("mechanics_context") if isinstance(context.get("mechanics_context"), dict) else {}
    for event in mechanics.get("forced_events") or []:
        if isinstance(event, dict):
            parts.append(str(event.get("kind") or ""))
            parts.append(str(event.get("summary") or ""))
    for event in context.get("gm_events") or []:
        if isinstance(event, dict) and (event.get("force") or event.get("due")):
            parts.append(str(event.get("summary") or ""))
    return "\n".join(parts)


def _named_in(text: str, name: str, code: str = "") -> bool:
    label = str(name or "").strip()
    if len(label) >= 3 and re.search(rf"(?<![A-Za-z0-9]){re.escape(label)}(?![A-Za-z0-9])", text, re.I):
        return True
    token = str(code or "").strip()
    if token and re.search(rf"\[\[{re.escape(token)}\]\]", text, re.I):
        return True
    if len(token) >= 2 and re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", text):
        return True
    return False


def _is_travel(context: dict[str, Any], player_input: str) -> bool:
    contract = context.get("movement_contract")
    if isinstance(contract, dict) and contract.get("travel_intent"):
        return True
    return bool(_TRAVEL_RE.search(str(player_input or "")))


def _weather_view(context: dict[str, Any]) -> dict[str, Any] | None:
    mechanics = context.get("mechanics_context") if isinstance(context.get("mechanics_context"), dict) else {}
    raw = mechanics.get("weather") if isinstance(mechanics.get("weather"), dict) else None
    if raw is None and isinstance(context.get("weather"), dict):
        raw = context.get("weather")
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip()
    label = str(raw.get("label") or kind).strip()
    if not kind and not label:
        return None
    view: dict[str, Any] = {}
    if kind:
        view["kind"] = kind
    if label:
        view["label"] = label
    announce = mechanics.get("weather_announce") or raw.get("announce")
    if announce:
        view["announce"] = _one_line(announce, 200)
    return view


def _map_view(context: dict[str, Any], player_input: str) -> dict[str, Any] | None:
    """Standing tile, the stretch's people-leaning, and exits only while walking."""
    space = context.get("map_space") if isinstance(context.get("map_space"), dict) else None
    if not space:
        return None
    view: dict[str, Any] = {}
    player = space.get("player") if isinstance(space.get("player"), dict) else {}
    terrain = str(player.get("terrain") or "").strip()
    if terrain:
        view["tile"] = {"terrain": terrain}
    leaning = space.get("people_leaning") if isinstance(space.get("people_leaning"), dict) else None
    if leaning:
        local: dict[str, Any] = {}
        if leaning.get("majority"):
            local["majority"] = leaning.get("majority")
        kind = str(leaning.get("kind") or "").strip()
        if kind:
            local["kind"] = kind
        option = str(leaning.get("option") or "").strip()
        if option:
            local["option"] = option
        if local:
            view["people_leaning"] = local
    if _is_travel(context, player_input):
        view["step_budget"] = int(space.get("step_budget") or 4)
        exits = space.get("exits") if isinstance(space.get("exits"), dict) else {}
        slim_exits: dict[str, Any] = {}
        for name, info in exits.items():
            if isinstance(info, dict):
                slim_exits[str(name)] = {"status": info.get("status") or "", "terrain": info.get("terrain") or ""}
            else:
                slim_exits[str(name)] = {"status": str(info)}
        if slim_exits:
            view["exits"] = slim_exits
    return view or None


def _location_with_people(context: dict[str, Any]) -> dict[str, Any]:
    current = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    if current.get("npcs"):
        return current
    cid = current.get("id")
    code = str(current.get("code") or "")
    for loc in context.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        if cid and loc.get("id") == cid:
            return loc
        if code and str(loc.get("code") or "") == code:
            return loc
    return current


def _place_view(context: dict[str, Any]) -> dict[str, Any] | None:
    current = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
    source = _location_with_people(context)
    place: dict[str, Any] = {}
    name = str(current.get("name") or source.get("name") or "").strip()
    code = str(current.get("code") or source.get("code") or "").strip()
    if name:
        place["name"] = name
    if code:
        place["code"] = code
    # Inside a venue: what it is and who keeps it. Around it: the doors here, so
    # a shop already on record is walked back into rather than reinvented.
    if current.get("inside_venue"):
        kind = str(current.get("venue_kind") or "").replace("_", " ")
        if kind:
            place["kind"] = kind
        keeper = current.get("keeper") if isinstance(current.get("keeper"), dict) else {}
        if keeper.get("name"):
            place["keeper"] = str(keeper["name"])
    doors = [
        str(v.get("name") or "")
        for v in current.get("venues_here") or []
        if isinstance(v, dict) and str(v.get("name") or "").strip() and str(v.get("name")) != name
    ]
    if doors:
        place["venues_here"] = doors[:8]
    here_id = int(current.get("id") or source.get("id") or 0)
    people = []
    for npc in (source.get("npcs") or [])[:12]:
        if not isinstance(npc, dict):
            continue
        person = str(npc.get("name") or "").strip()
        if not person:
            continue
        entry = {"name": person, "code": npc.get("code") or "", "role": npc.get("role") or ""}
        # Whose place this is (playtest #16): someone whose workplace is
        # elsewhere is a visitor here, not the one behind the counter.
        workplace_id = int(npc.get("workplace_id") or 0)
        if workplace_id and here_id and workplace_id == here_id:
            entry["works_here"] = True
        elif npc.get("workplace"):
            entry["works_at"] = str(npc.get("workplace"))
        people.append(entry)
    if people:
        place["people"] = people
    return place or None


def _appearance(context: dict[str, Any]) -> str:
    options = ((context.get("settings") or {}).get("playthrough_options") or {})
    if isinstance(options, dict):
        text = str(options.get("appearance") or "").strip()
        if text:
            return text
    player = context.get("player") if isinstance(context.get("player"), dict) else {}
    return str(player.get("appearance") or "").strip()


def _player_view(context: dict[str, Any]) -> dict[str, Any] | None:
    player = context.get("player") if isinstance(context.get("player"), dict) else {}
    view: dict[str, Any] = {}
    for key in ("name", "public_name", "title", "race"):
        if player.get(key):
            view[key] = player.get(key)
    worn = []
    for item in context.get("inventory") or []:
        if not isinstance(item, dict):
            continue
        slot = str(item.get("equipped_slot") or "").strip()
        item_name = str(item.get("name") or "").strip()
        if not slot or not item_name:
            continue
        worn.append({"name": item_name, "code": item.get("code") or "", "slot": slot})
    if worn:
        view["worn"] = worn
    alias = context.get("active_player_alias")
    if isinstance(alias, dict) and str(alias.get("active") or "").strip() in {"1", "true", "True"} and alias.get("alias"):
        view["known_as"] = alias.get("alias")
    return view or None


def _person_line(context: dict[str, Any], person: dict[str, Any]) -> str:
    code = str(person.get("code") or "")
    name = str(person.get("name") or "")
    for loc in context.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        for npc in loc.get("npcs") or []:
            if not isinstance(npc, dict):
                continue
            same_code = code and str(npc.get("code") or "") == code
            same_name = name and str(npc.get("name") or "") == name
            if same_code or same_name:
                return _one_line(npc.get("summary"))
    return ""


def _matched_templates(context: dict[str, Any], focus: str) -> dict[str, Any]:
    options = ((context.get("settings") or {}).get("playthrough_options") or {})
    if not isinstance(options, dict):
        return {}
    templates = options.get("setting_templates") if isinstance(options.get("setting_templates"), dict) else {}
    matched: dict[str, Any] = {}
    for key, row in templates.items():
        raw = _TEMPLATE_CUES.get(str(key)) or ()
        cues = (raw,) if isinstance(raw, str) else raw
        if not any(re.search(cue, focus, re.I) for cue in cues):
            continue
        rule = row.get("rule") if isinstance(row, dict) else row
        text = str(rule or "").strip()[:900]
        if text:
            matched[str(key)] = {"rule": text}
    return matched


def _named_records(context: dict[str, Any], focus: str, here_codes: set[str]) -> dict[str, Any]:
    named: dict[str, Any] = {}
    people = []
    for loc in context.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        for npc in loc.get("npcs") or []:
            if not isinstance(npc, dict):
                continue
            code = str(npc.get("code") or "")
            if code and code in here_codes:
                continue
            if not _named_in(focus, str(npc.get("name") or ""), code):
                continue
            people.append({
                "name": npc.get("name") or "",
                "code": code,
                "role": npc.get("role") or "",
                "line": _one_line(npc.get("summary")),
            })
    if people:
        named["people"] = people[:4]
    items = []
    for item in context.get("inventory") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("equipped_slot") or "").strip():
            continue
        code = str(item.get("code") or "")
        if not _named_in(focus, str(item.get("name") or ""), code):
            continue
        items.append({
            "name": item.get("name") or "",
            "code": code,
            "line": _one_line(item.get("description") or item.get("item_type")),
        })
    if items:
        named["items"] = items[:4]
    abilities = []
    for ability in context.get("abilities") or []:
        if not isinstance(ability, dict):
            continue
        code = str(ability.get("code") or "")
        if not _named_in(focus, str(ability.get("name") or ""), code):
            continue
        abilities.append({
            "name": ability.get("name") or "",
            "code": code,
            "line": _one_line(ability.get("description")),
        })
    if abilities:
        named["abilities"] = abilities[:3]
    skills = []
    for skill in context.get("skills") or []:
        if not isinstance(skill, dict):
            continue
        code = str(skill.get("code") or "")
        if not _named_in(focus, str(skill.get("name") or ""), code):
            continue
        skills.append({
            "name": skill.get("name") or "",
            "code": code,
            "line": _one_line(skill.get("notes") or skill.get("description")),
        })
    if skills:
        named["skills"] = skills[:3]
    return named


def _combat_view(mechanics: dict[str, Any]) -> dict[str, Any] | None:
    combat = mechanics.get("combat") if isinstance(mechanics.get("combat"), dict) else None
    if not combat:
        return None
    status = str(combat.get("status") or "")
    if status in {"", "not_combat"}:
        return {"status": "not_combat"}
    attack = combat.get("player_attack") if isinstance(combat.get("player_attack"), dict) else {}
    target = combat.get("target") if isinstance(combat.get("target"), dict) else {}
    resolution = combat.get("resolution") if isinstance(combat.get("resolution"), dict) else {}
    view: dict[str, Any] = {"status": status}
    if attack.get("weapon"):
        view["player_attack"] = {"weapon": attack.get("weapon")}
    if target.get("name") or target.get("code"):
        view["target"] = {"name": target.get("name") or "", "code": target.get("code") or ""}
    if resolution:
        view["resolution"] = {
            "outcome": resolution.get("outcome"),
            "damage": resolution.get("damage"),
            "target_health_after": resolution.get("target_health_after"),
        }
    return view


def _mechanics_view(context: dict[str, Any]) -> dict[str, Any] | None:
    mechanics = context.get("mechanics_context") if isinstance(context.get("mechanics_context"), dict) else {}
    view: dict[str, Any] = {}
    weather = _weather_view(context)
    if weather:
        announce = weather.pop("announce", None)
        view["weather"] = weather
        if announce:
            view["weather_announce"] = announce
    combat = _combat_view(mechanics)
    if combat:
        view["combat"] = combat
    ability = mechanics.get("ability_use") if isinstance(mechanics.get("ability_use"), dict) else None
    if ability:
        record = ability.get("ability") if isinstance(ability.get("ability"), dict) else {}
        view["ability_use"] = {
            "ok": ability.get("ok"),
            "blocked": ability.get("blocked"),
            "name": record.get("name") or ability.get("name") or "",
            "code": record.get("code") or "",
            "reasons": list(ability.get("reasons") or [])[:3],
        }
    forced = []
    for event in mechanics.get("forced_events") or []:
        if not isinstance(event, dict):
            continue
        forced.append({"kind": event.get("kind") or "", "summary": _one_line(event.get("summary"), 180)})
    if forced:
        view["forced_events"] = forced[:4]
    # play_turn rolls the action's checks before the model is called and the
    # system prompt tells the model to narrate them. The view did not carry
    # them, so a failed persuasion roll stored a cold attitude on the NPC and
    # the narrator, never told, wrote free cooperation anyway.
    checks = []
    for check in mechanics.get("resolved_checks") or []:
        if not isinstance(check, dict):
            continue
        skill = check.get("skill") if isinstance(check.get("skill"), dict) else {}
        row: dict[str, Any] = {
            "skill": skill.get("code") or check.get("skill_code") or "",
            "outcome": check.get("outcome") or "",
        }
        if check.get("degree"):
            row["degree"] = check.get("degree")
        if check.get("social_attitude"):
            row["attitude"] = check.get("social_attitude")
        if check.get("social_direction"):
            row["direction"] = _one_line(check.get("social_direction"), 240)
        if check.get("mishap"):
            row["mishap"] = _one_line(check.get("mishap"), 160)
        injury = check.get("injury") if isinstance(check.get("injury"), dict) else None
        if injury and injury.get("summary"):
            row["injury"] = _one_line(injury.get("summary"), 160)
        checks.append(row)
    if checks:
        view["resolved_checks"] = checks[:4]
    spend = mechanics.get("action_spend") if isinstance(mechanics.get("action_spend"), dict) else None
    if spend and (spend.get("blocked") or spend.get("collapse")):
        view["action_spend"] = {
            "blocked": bool(spend.get("blocked")),
            "kind": spend.get("kind") or "",
            "reasons": list(spend.get("reasons") or [])[:3],
        }
    collapse = mechanics.get("collapse")
    if isinstance(collapse, dict) and collapse:
        view["collapse"] = collapse
    elif isinstance(collapse, str) and collapse.strip():
        view["collapse"] = collapse.strip()[:200]
    reputation = mechanics.get("area_reputation")
    if isinstance(reputation, (int, float)) and not isinstance(reputation, bool) and int(reputation) != 0:
        view["area_reputation"] = int(reputation)
    social = mechanics.get("social_reputation") if isinstance(mechanics.get("social_reputation"), dict) else None
    if social:
        view["social_reputation"] = {
            key: social.get(key) for key in ("flavor", "npc_code", "walked_away") if social.get(key) is not None
        }
    codes = mechanics.get("player_inventory_codes")
    if isinstance(codes, list) and codes:
        view["player_inventory_codes"] = [str(code) for code in codes[:40]]
        if mechanics.get("player_inventory_truncated"):
            view["player_inventory_truncated"] = True
    return view or None


def _voice_view(context: dict[str, Any]) -> dict[str, Any] | None:
    voice = context.get("narrative_voice")
    if not isinstance(voice, dict):
        return None
    view: dict[str, Any] = {}
    rule = str(voice.get("rule") or "").strip()
    if rule:
        view["rule"] = rule
    pronouns = voice.get("player_pronouns")
    if isinstance(pronouns, dict) and pronouns:
        view["player_pronouns"] = pronouns
    return view or None


def _setup_choices(context: dict[str, Any]) -> dict[str, str]:
    """The player's own labels. The written essay stays out until the action names it."""
    options = ((context.get("settings") or {}).get("playthrough_options") or {})
    if not isinstance(options, dict):
        return {}
    templates = options.get("setting_templates") if isinstance(options.get("setting_templates"), dict) else {}
    try:
        from app.setting_templates import TEMPLATE_SPECS

        keys = [str(spec.get("key") or "") for spec in TEMPLATE_SPECS]
    except Exception:
        keys = list(templates.keys())
    choices: dict[str, str] = {}
    for key in keys:
        if not key:
            continue
        row = templates.get(key) if isinstance(templates, dict) else None
        choice = str(row.get("choice") or "").strip() if isinstance(row, dict) else ""
        if not choice:
            raw = options.get(key)
            choice = raw.strip() if isinstance(raw, str) else ""
        if choice and choice.lower() != "custom":
            choices[key] = choice[:160]
    return choices


def _draft_text(draft: Any) -> str:
    """Names and sentences the scene already wrote, so the check can look those up."""
    if not isinstance(draft, dict):
        return ""
    parts = [str(draft.get("narration") or "")]
    for segment in draft.get("narration_segments") or []:
        if isinstance(segment, dict):
            parts.append(str(segment.get("text") or ""))
        elif segment:
            parts.append(str(segment))
    for key in ("npcs", "inventory", "items", "abilities", "skills", "locations"):
        rows = draft.get(key)
        if isinstance(rows, dict):
            rows = list(rows.values())
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            parts.append(str(row.get("name") or ""))
            parts.append(str(row.get("code") or ""))
    return "\n".join(part for part in parts if part)


def _visible_world(context: dict[str, Any], player_input: str, extra_focus: str = "") -> dict[str, Any]:
    """Titles plus what the player can see. Sheets stay out until named."""
    focus = _focus_text(context, player_input, extra_focus)
    world: dict[str, Any] = {}
    if context.get("world_time") is not None:
        world["world_time"] = context.get("world_time")
    if context.get("turn") is not None:
        world["turn"] = context.get("turn")

    settings_out: dict[str, Any] = {}
    setup = context.get("settings") if isinstance(context.get("settings"), dict) else {}
    if "setup_complete" in setup:
        settings_out["setup_complete"] = setup.get("setup_complete")
    options_out: dict[str, Any] = {}
    appearance = _appearance(context)
    if appearance:
        options_out["appearance"] = appearance
    choices = _setup_choices(context)
    if choices:
        options_out["choices"] = choices
    rules = _matched_templates(context, focus)
    if rules:
        options_out["setting_templates"] = rules
    if options_out:
        settings_out["playthrough_options"] = options_out
    if settings_out:
        world["settings"] = settings_out

    player = _player_view(context)
    if player:
        for worn in player.get("worn") or []:
            if not _named_in(focus, str(worn.get("name") or ""), str(worn.get("code") or "")):
                continue
            for item in context.get("inventory") or []:
                if not isinstance(item, dict):
                    continue
                same = str(item.get("code") or "") == str(worn.get("code") or "") or str(item.get("name") or "") == str(worn.get("name") or "")
                if same:
                    line = _one_line(item.get("description") or item.get("item_type"))
                    if line:
                        worn["line"] = line
                    break
        world["player"] = player

    place = _place_view(context)
    if place:
        for person in place.get("people") or []:
            if _named_in(focus, str(person.get("name") or ""), str(person.get("code") or "")):
                line = _person_line(context, person)
                if line:
                    person["line"] = line
        world["current_location"] = place

    space = _map_view(context, player_input)
    if space:
        world["map_space"] = space
    mechanics = _mechanics_view(context)
    if mechanics:
        world["mechanics_context"] = mechanics
    voice = _voice_view(context)
    if voice:
        world["narrative_voice"] = voice

    hint = context.get("direction_hint") if isinstance(context.get("direction_hint"), dict) else None
    if hint:
        kept = {key: hint.get(key) for key in ("told", "wording", "reason") if key in hint}
        world["direction_hint"] = kept or hint
    offers = context.get("open_offers")
    if isinstance(offers, list) and offers:
        slim_offers = []
        for row in offers[:8]:
            if isinstance(row, dict):
                slim_offers.append({"title": row.get("title") or "", "source": row.get("source") or ""})
            else:
                slim_offers.append(row)
        world["open_offers"] = slim_offers
    if context.get("naming_contract"):
        world["naming_contract"] = context.get("naming_contract")
    if context.get("recall_contract"):
        world["recall_contract"] = context.get("recall_contract")
    psychology = context.get("npc_psychology_context")
    if isinstance(psychology, str) and psychology.strip():
        world["npc_psychology_context"] = psychology.strip()[:1800]
    checks_ctx = context.get("skill_check_context")
    if isinstance(checks_ctx, dict) and checks_ctx.get("dice_checks_enabled"):
        active = [row for row in checks_ctx.get("active_skills") or [] if isinstance(row, dict) and row.get("code")]
        if active:
            world["skill_check_context"] = {
                "active_skills": [{"code": row["code"], "name": row.get("name") or ""} for row in active[:8]]
            }

    # Engine rows for the races present and the lore this turn touches,
    # already budgeted in app/world_facts.py (playtest #8).
    facts = context.get("world_facts")
    if isinstance(facts, dict) and (facts.get("races") or facts.get("facts")):
        world["world_facts"] = {key: facts[key] for key in ("races", "facts") if facts.get(key)}

    here_codes = {str(person.get("code") or "") for person in (place or {}).get("people") or [] if person.get("code")}
    named = _named_records(context, focus, here_codes)
    if named:
        world["named"] = named

    # Who the player is talking to, decided by the engine (app/conversation.py).
    from app.conversation import world_view as conversation_world_view

    talk = conversation_world_view(context.get("conversation_turn"))
    if talk:
        world["conversation_turn"] = talk
    # What the player is in the middle of, kept by the engine (app/scene_thread.py).
    from app.scene_thread import world_view as scene_thread_view

    thread = scene_thread_view(context.get("scene_thread"))
    if thread:
        world["scene_thread"] = thread
    talking_codes = {str(row.get("code") or "") for row in (talk or {}).get("talking_to") or []}
    if _TALK_RE.search(focus):
        conversations = context.get("conversations") if isinstance(context.get("conversations"), list) else []
        latest = conversations[0] if conversations and isinstance(conversations[0], dict) else None
        # The newest logged line belongs to whoever said it. Shown while the
        # player talks to someone else, it pulled the draft back to them
        # (playtest #6: Aria's old line, an untagged reply meant for Ashwalker).
        if latest and talking_codes and str(latest.get("npc_code") or latest.get("code") or "") not in talking_codes:
            latest = None
        if latest:
            world["conversations"] = [{
                "npc": latest.get("npc_name") or latest.get("name") or "",
                "code": latest.get("npc_code") or latest.get("code") or "",
                "line": _one_line(latest.get("summary") or latest.get("topic") or latest.get("text")),
            }]
    # The player's quests ride every turn, small: title, code and the step
    # they are on. This used to need the word "quest" or "job" in the focus
    # text, and the handoff dropped the key besides, so it never showed.
    quests_view = []
    for quest in context.get("active_quests") or []:
        if not (isinstance(quest, dict) and quest.get("title")):
            continue
        entry = {"title": _one_line(quest.get("title"))[:80], "code": quest.get("code") or ""}
        objective = _one_line(quest.get("current_objective") or "")
        if objective:
            entry["now"] = objective[:160]
        if quest.get("turns_remaining"):
            entry["turns_left"] = quest.get("turns_remaining")
        quests_view.append(entry)
    if quests_view:
        world["active_quests"] = quests_view[: 6 if _QUEST_RE.search(focus) else 4]
    asks = context.get("relevant_asks")
    if isinstance(asks, list) and asks:
        lines = [str(item)[:240] for item in asks[:3] if str(item).strip()]
        if lines:
            world["relevant_asks"] = lines
    if _is_travel(context, player_input):
        contract = context.get("movement_contract") if isinstance(context.get("movement_contract"), dict) else {}
        current = contract.get("current_location") if isinstance(contract.get("current_location"), dict) else {}
        travel_view: dict[str, Any] = {
            "travel_intent": True,
            "current_location": {
                "name": current.get("name") or (place or {}).get("name") or "",
                "code": current.get("code") or (place or {}).get("code") or "",
            },
        }
        known = [str(name) for name in (contract.get("known_places") or []) if str(name or "").strip()]
        if known:
            travel_view["known_places"] = known[:10]
        # Where each known place lies and which way this walk goes, decided by
        # the engine before the draft writes (playtest #33).
        bearings = contract.get("bearings") if isinstance(contract.get("bearings"), dict) else {}
        if bearings:
            travel_view["bearings"] = {str(k): str(v) for k, v in list(bearings.items())[:10]}
        plan = contract.get("walk_plan") if isinstance(contract.get("walk_plan"), dict) else {}
        if plan.get("direction"):
            toward = f" toward {plan['toward']}" if plan.get("toward") else ""
            travel_view["walk_plan"] = (
                f"A walk this turn goes {plan['direction']}{toward}. Narrate that heading; WALK says {plan['direction']}."
            )
        venues = []
        for venue in contract.get("venues_here") or []:
            if isinstance(venue, dict) and str(venue.get("name") or "").strip():
                venues.append({"name": venue.get("name"), "kind": venue.get("kind") or ""})
        if venues:
            travel_view["venues_here"] = venues[:8]
        # Prose and position must agree (playtest #20): without a move the
        # engine keeps the player here, so the scene has to keep them here too.
        here_name = travel_view["current_location"]["name"] or "the current place"
        travel_view["no_move_means"] = f"the player is still in {here_name} at the end of the turn"
        from app.scene_thread import follow_target

        followed = follow_target(player_input)
        if followed:
            travel_view["following"] = followed
        world["movement_contract"] = travel_view
    return world


def _scene_instruction(turn_kind: str, world: dict[str, Any], *, checking: bool) -> str:
    if checking:
        text = (
            "This pass reads the same titles, plus one line for anything the draft named. "
            "Return a verdict object: verdict, issues, and a patch of only the draft_turn keys that must change. "
            "Narration that already answers the action stays out of the patch. "
            "Do not add a fact that was not included. "
        )
    else:
        text = (
            "This pass reads titles and what is in front of the player, then writes the scene. "
            "Continue one turn. opening_scene = first scene before the player acts. "
            "continue_scene = advance without inventing a player action. "
            "wait_scene = narrate spent time only using resolved rng. "
            "event_scene = narrate a decided world-event pack. "
        )
    if turn_kind == "wait_scene":
        text += "world_time already advanced; rng lines in player_input are binding; no extra major events. "
    elif turn_kind == "event_scene":
        text += "The event pack is binding. Do not invent player gear. "
    elif turn_kind in {"opening_scene", "continue_scene"} and checking:
        text += "Do not invent a player action. "
    text += (
        "When world_state.map_space.tile is present, that is the ground underfoot. "
        "When world_state.map_space.people_leaning is present, that is who might live on this stretch: "
        "a chance, not a crowd that must appear, and not a census. "
        "When world_state.mechanics_context.weather is present, that is the sky. Do not invent a different sky. "
        "When world_state.movement_contract.travel_intent is true, the walk stops at map_space.step_budget "
        "and map_space.exits. Do not invent ground past that. "
        "playthrough_options.appearance and player.worn are the clothes and armour in view. "
        "When world_state.direction_hint is present and direction_hint.told is true, "
        "say direction_hint.wording and do not add another place or a coordinate. "
        "When world_state.direction_hint is present and told is false, do not name a location for that question. "
        "When world_state.open_offers is present, those jobs are posted and not yet taken. "
        "The player can accept one. The story may offer other work that fits the scene and quest_style, "
        "but not a pile of offers at once. "
        "When world_state.active_quests is present, those are the player's jobs and the step each is on; "
        "keep them consistent, and let the story move a step only when the player's action earns it. "
        "When world_state.naming_contract is present the player asked for a name: "
        "write naming_contract.name in the narration as plain text. Never describe a name without giving it. "
        "When world_state.recall_contract is present the player is answering something this "
        "world already knows: write recall_contract.specifics into the narration as plain "
        "text. Restating the question ('you answer honestly who you owe, how much') is not an answer. "
        "When world_state.mechanics_context.resolved_checks is present, those dice already fell: "
        "narrate each listed outcome and attitude as it stands. Do not re-roll, soften a failure, "
        "or grant the cooperation a failed social check denied. "
        "When world_state.npc_psychology_context is present, it is private narrator knowledge about "
        "people in the scene: let it steer what they do and withhold. Never read it out as fact "
        "unless the scene itself reveals it. "
        "When world_state.skill_check_context is present, name a check only by one of its "
        "active_skills codes. "
        "When world_state.conversation_turn is present, the engine already decided who the player is talking to: "
        "the people in conversation_turn.talking_to answer the player; people in conversation_turn.listening may "
        "react but do not answer for them. The player's own quoted words are spoken by the player only. "
    )
    if world.get("movement_contract"):
        text += (
            "A move is the only thing that changes where the player is. When the turn has no move, "
            "movement_contract.no_move_means holds: the prose keeps the player in that place and does not take "
            "them into another place or building. When movement_contract.following is present, the player goes "
            "after that one: if they lead somewhere else, name that place with a move; otherwise the pursuit "
            "stays inside the current place. "
        )
    if world.get("scene_thread"):
        text += (
            "world_state.scene_thread is what the player is in the middle of right now, kept by the engine. "
            "This turn's action happens inside it: a side action such as examining something or asking a "
            "question does not end it, replace it, or send its target or the people with_the_player away. "
            "Keep them where the thread left them. The thread ends only when the player drops it, finishes it, "
            "or the scene itself resolves it. "
        )
        if checking:
            text += (
                "A draft that forgets scene_thread on a side action, or swaps it for an unrelated errand, "
                "is an issue. "
            )
    if world.get("world_facts"):
        text += (
            "When world_state.world_facts is present, those rows are this world's stored facts. "
            "world_facts.races gives each people's magic access and rules; here lists who in the scene is of that people. "
            "A person whose people has magic none does not cast or use magic. "
            "Keep people, magic, customs and lore consistent with world_facts.facts. "
        )
    options = (world.get("settings") or {}).get("playthrough_options") or {}
    if isinstance(options, dict) and isinstance(options.get("choices"), dict) and options["choices"]:
        text += (
            "playthrough_options.choices are this playthrough's labels. "
            "For rank_scale, use only the rungs named there. "
        )
    templates = options.get("setting_templates") if isinstance(options, dict) else None
    if isinstance(templates, dict) and templates:
        text += (
            "When world_state.settings.playthrough_options.setting_templates is present, "
            "follow that stored rule. Do not replace its labels. "
        )
    if not checking:
        text += "Prefer existing codes. The database wins over invention."
    return text


def build_user_prompt(context: dict[str, Any], player_input: str) -> str:
    turn_kind = _turn_kind_for(player_input)
    world = _visible_world(context, player_input)
    return json.dumps(
        {
            "world_state": world,
            "turn_kind": turn_kind,
            "player_input": player_input,
            "instruction": _scene_instruction(turn_kind, world, checking=False),
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )


def build_verify_prompt(context: dict[str, Any], player_input: str, draft: dict[str, Any]) -> str:
    turn_kind = _turn_kind_for(player_input)
    world = _visible_world(context, player_input, extra_focus=_draft_text(draft))
    return json.dumps(
        {
            "world_state": world,
            "turn_kind": turn_kind,
            "player_input": player_input,
            "draft_turn": draft,
            "instruction": _scene_instruction(turn_kind, world, checking=True),
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
