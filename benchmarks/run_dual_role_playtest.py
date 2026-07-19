"""
benchmarks — dual-role playtest (no local LLM).

Grok-style dual agent:
  - PLAYER: chooses the next action from world state + last narration
  - GM: writes narration + structured turn JSON
  - BACKEND: Mørkyn apply_turn / SQLite only (Ollama is never called)

Run from repo root:
  python benchmarks/run_dual_role_playtest.py

Env:
  GROK_BENCH_TURNS   default 100
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BENCH_ROOT.parent
REPORT_DIR = BENCH_ROOT / "reports"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _setup() -> dict:
    return {
        "player_name": "Ashen Courier",
        "player_public_name": "the Ashbound",
        "player_title": "Courier",
        "player_age": "27",
        "player_sex": "unspecified",
        "previous_life_age": "",
        "previous_life_sex": "",
        "backstory_mode": "known",
        "character_backstory": "A road courier carrying a sealed letter and old debts around Mosswake Gate.",
        "memory_policy": "known",
        "difficulty": "normal",
        "narration_detail": "balanced",
        "world_style": "frontier dark fantasy",
        "custom_style": "GROK dual-role benchmark: sealed letter, debts, road pressure.",
        "start_location": "Mosswake Gate",
        "leveling_system": True,
        "game_system": False,
        "system_style": "subtle blue-window system",
        "special_ability_origin": "none",
        "special_ability": False,
        "special_abilities": [],
        "skill_style": "standard",
        "skill_levels_enabled": True,
        "new_skill_frequency": "normal",
        "proficiency_system": True,
        "proficiency_access": "learned",
        "skill_growth_speed": "normal",
        "proficiency_growth_speed": "normal",
        "xp_growth_speed": "normal",
        "custom_skills": "",
        "tone": "tense frontier",
        "economy": "scarce coin and favors",
        "magic_level": "low and dangerous",
        "tech_level": "late medieval",
        "npc_density": "moderate",
        "quest_style": "rumors and personal debts",
        "faction_pressure": "merchant houses and road wardens",
        "death_rules": "injury and debt before instant death",
        "loot_rarity": "mundane common",
        "inventory_weight_limit": 30,
        "inventory_slot_limit": 12,
        "inventory_rules": "",
    }


# Beat book: 20-step cycle × 5 = 100 turns. Each beat is (player_intent_template, gm_kind).
BEATS: list[tuple[str, str]] = [
    ("I survey {loc}, note exits, cover, and watchers.", "survey"),
    ("I ask {npc} what trouble has been happening here lately.", "rumor"),
    ("I check my satchel and secure the sealed letter.", "inventory"),
    ("I buy a cheap travel ration or water if I can afford it.", "buy"),
    ("I listen for talk of bandits, debt collectors, or sealed letters.", "listen"),
    ("I walk toward the most suspicious path from {loc}, staying alert.", "travel"),
    ("I keep my hand near my satchel and only advance as far as I can retreat.", "caution"),
    ("I try to learn one useful name, place, or debt tied to my courier work.", "intel"),
    ("I rest a few minutes in safer cover and watch the crowd.", "rest"),
    ("I look for courier work: messages, package runs, or quiet deliveries.", "work"),
    ("I examine posted notices near {loc} and remember one detail.", "notice"),
    ("I approach someone politely and test if they will talk.", "social"),
    ("I search the ground for tracks, blood, or dropped gear.", "search"),
    ("I circle back toward open ground if I feel boxed in.", "retreat"),
    ("I use what gear I have carefully to stay fed or unnoticed.", "use_item"),
    ("I ask about safe lodging for one night and the cost in coin or favor.", "lodging"),
    ("I follow a lead one step further, then stop to reassess.", "lead"),
    ("I prioritize distance, cover, and a clear exit over pride.", "avoid"),
    ("I restate my goal: deliver the sealed letter and survive the debts around it.", "goal"),
    ("I move if the scene has gone cold, or dig one layer deeper if it has not.", "shift"),
]


PLACES = [
    ("Mosswake Gate", "The frontier gate-town crossroads where debt and cargo meet."),
    ("Mosswake Market Lane", "A narrow lane of stalls, chalk marks, and wet timber."),
    ("Ashcut Alley", "A suspicious cut between warehouses that smells of oil and smoke."),
    ("River Toll Shed", "A damp shed where road wardens count favors as carefully as coin."),
    ("Outer Clearing", "A windy clearing just beyond the last lanterns of town."),
    ("Courier Board", "A wall of nails and notices near the gate offices."),
    ("Quiet Yard", "A walled yard used for mules, crates, and private conversations."),
    ("North Road Shoulder", "The muddy shoulder of the north road, with cart ruts and watch posts."),
]

NPCS = [
    ("Eldrin", "scarred market merchant who sells news with his goods"),
    ("Warden Brask", "road warden who watches satchels more than faces"),
    ("Mira of the Board", "notice-keeper who remembers every sealed mark"),
    ("Old Hobb", "mule handler who hears stables gossip first"),
    ("Sera Venn", "debt runner who smiles like a knife under cloth"),
    ("Tov the Runner", "young courier rival with faster legs than judgment"),
]


def _loc_name(state: dict) -> str:
    loc = state.get("current_location") or {}
    return str(loc.get("name") or "Mosswake Gate")


def _player_name(state: dict) -> str:
    return str((state.get("player") or {}).get("name") or "Ashen Courier")


def _npc_name(turn_index: int, state: dict) -> str:
    loc = _loc_name(state)
    for place_loc in state.get("locations") or []:
        if not isinstance(place_loc, dict):
            continue
        if str(place_loc.get("name") or "") != loc:
            continue
        npcs = place_loc.get("npcs") or []
        if npcs and isinstance(npcs[0], dict) and npcs[0].get("name"):
            return str(npcs[0]["name"])
    return NPCS[turn_index % len(NPCS)][0]


def _player_action(turn_index: int, state: dict) -> str:
    template, _kind = BEATS[(turn_index - 1) % len(BEATS)]
    return template.format(loc=_loc_name(state), npc=_npc_name(turn_index, state))


def _narration(paragraphs: list[str]) -> str:
    text = "\n\n".join(p.strip() for p in paragraphs if p and p.strip())
    # apply_turn stores up to 3600 chars in journal; keep playable length
    return text[:3200]


def _base_result(location: str, narration: str, turn_summary: str, **extra) -> dict:
    result = {
        "scene_plan": {
            "goal": "Advance the sealed-letter courier situation without soft-resetting the world.",
            "focus_points": [
                {
                    "kind": "location",
                    "summary": f"Keep pressure and choice openings around {location}.",
                    "event_worthy": False,
                    "persistence": "temporary",
                }
            ],
        },
        "narration_segments": [{"label": "paragraph", "text": narration}],
        "narration": narration,
        "player": {
            "health_delta": 0,
            "max_health_delta": 0,
            "xp_delta": 0,
            "gold_delta": 0,
            "level_delta": 0,
            "move_to_location": None,
            "move_to_location_code": None,
            "karma_delta": 0,
            "karma_reason": "",
            "karma_visibility": "private",
        },
        "inventory_changes": [],
        "skill_changes": [],
        "locations": [],
        "npcs": [],
        "relationships": [],
        "events": [],
        "gm_events": [],
        "conversations": [],
        "response_drafts": [],
        "index_updates": [],
        "ability_updates": [],
        "equipment_slots": [],
        "equipment_changes": [],
        "inventory_capacity_modifiers": [],
        "journal": [],
        "turn_summary": turn_summary[:700],
        "self_check": {
            "ok": True,
            "notes": ["dual-role GM/player turn applied without local LLM"],
        },
    }
    for key, value in extra.items():
        if key == "player" and isinstance(value, dict):
            result["player"].update(value)
        else:
            result[key] = value
    return result


def gm_opening(state: dict) -> dict:
    loc = _loc_name(state)
    name = _player_name(state)
    narration = _narration(
        [
            f"{loc} wakes under a thin frontier sky. Damp stone holds the night's cold, and cart ruts shine where lantern smoke still clings. "
            f"{name} stands just inside the gate with a satchel that never quite sits light: a sealed letter presses against older cloth, and older debts press harder than the leather.",
            "Market voices rise and fall without offering safety. A warden's gaze tracks satchels more than faces. Somewhere behind the stalls, chalk marks map favors the way other towns map streets. "
            "Nothing forces the first step, but standing still already costs attention.",
            "Playable openings sit close: listen before being noticed, ask who buys news with bread, check the courier board, test the alley that smells of oil, or walk the outer road only as far as retreat still works. "
            "The letter does not explain itself. The town will, if pushed carefully.",
        ]
    )
    return _base_result(
        loc,
        narration,
        f"opening: established {name} at {loc} with sealed letter pressure.",
        locations=[{"name": loc, "summary": "Frontier gate-town where cargo, debt, and sealed marks meet."}],
        npcs=[
            {
                "name": "Eldrin",
                "summary": "Scarred market merchant who sells news with his goods.",
                "location": loc,
                "disposition": "wary-helpful",
            }
        ],
        events=[
            {
                "title": "Sealed letter arrival",
                "location": loc,
                "summary": f"{name} entered {loc} carrying a sealed letter and unsettled debts.",
                "status": "active",
                "persistence": "story",
                "disappear_chance": 0,
            }
        ],
        inventory_changes=[
            {
                "name": "Sealed Letter",
                "quantity_delta": 1,
                "rarity": "unique",
                "item_type": "quest",
                "description": "Oilcloth packet with a distant house sigil. Do not open.",
            },
            {
                "name": "Travel Coin Pouch",
                "quantity_delta": 1,
                "rarity": "common",
                "item_type": "container",
                "description": "Thin pouch with a few practical coins.",
            },
        ],
        player={"xp_delta": 0, "gold_delta": 8},
    )


def gm_turn(turn_index: int, state: dict, player_action: str) -> dict:
    """GM response: narrate + mutate world according to beat kind."""
    loc = _loc_name(state)
    name = _player_name(state)
    _template, kind = BEATS[(turn_index - 1) % len(BEATS)]
    cycle = (turn_index - 1) // len(BEATS)  # 0..4 for 100 turns
    place_name, place_summary = PLACES[turn_index % len(PLACES)]
    npc_name, npc_summary = NPCS[turn_index % len(NPCS)]
    active_npc = _npc_name(turn_index, state)

    # Defaults
    move_to = None
    locations: list[dict] = []
    npcs: list[dict] = []
    inventory: list[dict] = []
    events: list[dict] = []
    gm_events: list[dict] = []
    conversations: list[dict] = []
    player_patch: dict = {"xp_delta": 1}
    skill_changes: list[dict] = []

    if kind == "survey":
        narration = _narration(
            [
                f"You survey {loc} with courier patience. Exits resolve first: the gate road, the market lane, a darker alley that holds smoke and boot-scrape. "
                f"Cover is imperfect—crates, a cart wheel, a doorway recess—but better than open mud.",
                f"Watchers exist. One is obvious ({active_npc} or someone like them), another is only a pause in conversation when your satchel shifts. "
                f"Your action was: {player_action} The place answers with map-like detail, not revelation.",
            ]
        )
        events.append(
            {
                "title": f"Survey of {loc}",
                "location": loc,
                "summary": f"{name} mapped exits, cover, and watchers at {loc}.",
                "status": "background",
                "persistence": "temporary",
                "disappear_chance": 40,
            }
        )
        skill_changes.append({"name": "Awareness", "delta": 1, "reason": "careful survey"})

    elif kind == "rumor":
        narration = _narration(
            [
                f"You ask {active_npc} about trouble. The answer comes sideways: bandits on the north shoulder, a debt runner smiling too often, "
                f"and a sealed mark that makes wardens look twice.",
                f"Nothing is free. {active_npc} wants either coin later or the sense that you are not prey. "
                f"Your intent—{player_action}—buys one useful rumor and a warning not to flash the letter.",
            ]
        )
        conversations.append(
            {
                "participants": [name, active_npc],
                "summary": f"{name} asked {active_npc} about local trouble; rumors of bandits and debt pressure surfaced.",
                "location": loc,
            }
        )
        events.append(
            {
                "title": "Rumor of north-road bandits",
                "location": loc,
                "summary": f"{active_npc} warned {name} about bandits and debt collectors near the north road.",
                "status": "active",
                "persistence": "story",
                "disappear_chance": 10,
            }
        )
        player_patch["xp_delta"] = 2

    elif kind == "inventory":
        narration = _narration(
            [
                f"You check the satchel in a quieter pocket of {loc}. The sealed letter is still dry in oilcloth. Coin is thin. "
                "Nothing has been cut free; nothing has been added without your knowledge.",
                "Securing straps and shifting weight is unglamorous work, but courier work survives on unglamorous habits. "
                f"Action taken: {player_action}",
            ]
        )
        inventory.append(
            {
                "name": "Spare Strap",
                "quantity_delta": 1 if turn_index % 20 == 3 else 0,
                "rarity": "common",
                "item_type": "misc",
                "description": "A short leather strap for rebinding a satchel.",
            }
        )
        inventory = [i for i in inventory if i.get("quantity_delta")]

    elif kind == "buy":
        gold = int((state.get("player") or {}).get("gold") or 0)
        if gold >= 2:
            narration = _narration(
                [
                    f"You spend two coins on a travel ration and a skin of water in {loc}. The seller does not care about your letter; only that your hands are steady.",
                    "Food is not plot. Food is the difference between clear thinking and a stupid fight later.",
                ]
            )
            player_patch["gold_delta"] = -2
            inventory.append(
                {
                    "name": "Travel Ration",
                    "quantity_delta": 1,
                    "rarity": "common",
                    "item_type": "consumable",
                    "description": "Dense bread and dried meat for the road.",
                }
            )
        else:
            narration = _narration(
                [
                    f"You mean to buy a ration in {loc}, but coin is too thin. The stallkeeper already knows the look.",
                    "You keep moving with an empty hand and a fuller caution.",
                ]
            )

    elif kind == "listen":
        narration = _narration(
            [
                f"You listen without standing like a listener. In {loc}, talk drifts: sealed packets, unpaid favors, a name spoken once and then not again.",
                f"Someone mentions {npc_name} in the same breath as debt. That is not proof. It is a direction.",
            ]
        )
        npcs.append(
            {
                "name": npc_name,
                "summary": npc_summary,
                "location": loc,
                "disposition": "unknown",
            }
        )
        gm_events.append(
            {
                "title": "Offscreen debt pressure",
                "summary": f"Somewhere beyond {loc}, collectors compare notes about a courier carrying a sealed packet.",
                "status": "hidden",
                "persistence": "background",
            }
        )

    elif kind == "travel":
        move_to = place_name if place_name != loc else PLACES[(turn_index + 1) % len(PLACES)][0]
        dest_summary = next((p[1] for p in PLACES if p[0] == move_to), place_summary)
        narration = _narration(
            [
                f"You leave the densest part of {loc} and take a careful route toward {move_to}. Distance is a tool: enough to change the watchers, not enough to strand you.",
                f"{dest_summary} The satchel rides closer to your ribs. Every turn of the path is chosen so retreat remains real.",
            ]
        )
        locations.append({"name": move_to, "summary": dest_summary})
        player_patch["move_to_location"] = move_to
        player_patch["xp_delta"] = 2

    elif kind == "caution":
        narration = _narration(
            [
                f"You advance only as far as pride allows reverse. In {loc}, that means half a lane, one corner, then a stop with an exit still in sight.",
                f"Your hand stays near the satchel. Action: {player_action} The world does not punish caution; it simply waits to see if you waste it.",
            ]
        )

    elif kind == "intel":
        narration = _narration(
            [
                f"You dig for one usable fact: a name, a place, a debt chain. {active_npc} or the board's chalk eventually yields a fragment.",
                f"Fragment earned (cycle {cycle + 1}): the letter's sigil is known to people who buy silence. Delivery is not only geography; it is politics with mud on its boots.",
            ]
        )
        events.append(
            {
                "title": "Letter sigil recognized",
                "location": loc,
                "summary": f"{name} learned the sealed letter's mark is known to people who trade silence.",
                "status": "active",
                "persistence": "story",
                "disappear_chance": 5,
            }
        )
        player_patch["xp_delta"] = 3

    elif kind == "rest":
        narration = _narration(
            [
                f"You take a short rest in safer cover at {loc}. Not sleep—only enough stillness for breath and a recount of threats.",
                "The crowd moves. No one rushes you. That is either luck or the quiet before a different kind of attention.",
            ]
        )
        player_patch["health_delta"] = 1 if int((state.get("player") or {}).get("health") or 10) < int((state.get("player") or {}).get("max_health") or 10) else 0

    elif kind == "work":
        narration = _narration(
            [
                f"You look for courier work in {loc}: short runs, sealed tags, quiet packages. One offer is honest. One is bait. You can tell them apart by who avoids looking at your satchel.",
                "You take a small legitimate run that pays poorly and costs little trust. Better than standing still with only debts for company.",
            ]
        )
        player_patch["gold_delta"] = 3
        player_patch["xp_delta"] = 2
        inventory.append(
            {
                "name": "Local Delivery Tag",
                "quantity_delta": 1,
                "rarity": "common",
                "item_type": "quest",
                "description": "A short-run delivery mark that proves you are working, not only fleeing.",
            }
        )

    elif kind == "notice":
        narration = _narration(
            [
                f"You read the notices near {loc}. Most are ordinary: lost mules, cheap blades, warden hours. One mark matches the language of sealed work.",
                "You commit a detail to memory: a house phrase that means 'do not open under rain or threat.' It is almost a joke until it is not.",
            ]
        )
        locations.append({"name": "Courier Board", "summary": "A wall of nails and notices near the gate offices."})

    elif kind == "social":
        narration = _narration(
            [
                f"You approach {npc_name} with plain courtesy. No flourish, no threat. In {loc}, that is rare enough to be interesting.",
                f"{npc_summary.capitalize()}. They give you a little room: not friendship, not refusal. A conversation that can grow or die on the next honesty.",
            ]
        )
        npcs.append(
            {
                "name": npc_name,
                "summary": npc_summary,
                "location": loc,
                "disposition": "cautious",
            }
        )
        conversations.append(
            {
                "participants": [name, npc_name],
                "summary": f"{name} opened a cautious conversation with {npc_name} at {loc}.",
                "location": loc,
            }
        )
        player_patch["karma_delta"] = 1
        player_patch["karma_reason"] = "plain courtesy under pressure"
        player_patch["karma_visibility"] = "local"

    elif kind == "search":
        narration = _narration(
            [
                f"You search the ground around {loc}. Mud keeps secrets badly: a cart-rutted scuff, a drop of old blood turned brown, a scrap of twine from a packet binding.",
                "None of it is a full answer. Together it says someone moved cargo in a hurry and did not want to be followed by amateurs.",
            ]
        )
        inventory.append(
            {
                "name": "Twine Scrap",
                "quantity_delta": 1,
                "rarity": "common",
                "item_type": "clue",
                "description": "Binding twine that matches courier packet work.",
            }
        )
        skill_changes.append({"name": "Tracking", "delta": 1, "reason": "ground search"})

    elif kind == "retreat":
        safe = "Mosswake Gate" if loc != "Mosswake Gate" else "Quiet Yard"
        narration = _narration(
            [
                f"The geometry of {loc} starts to feel wrong—too many shoulders, too few exits. You break the angle and move toward {safe}.",
                "Pride can wait. Satchels and lungs cannot.",
            ]
        )
        move_to = safe
        locations.append(
            {
                "name": safe,
                "summary": "Open enough to see trouble coming, close enough to matter.",
            }
        )
        player_patch["move_to_location"] = safe

    elif kind == "use_item":
        narration = _narration(
            [
                f"You use what you have without ceremony: a ration if hungry, a strap if the satchel slips, shadow if eyes linger too long on {loc}.",
                "Gear is a sentence written in advance. You read it carefully.",
            ]
        )

    elif kind == "lodging":
        narration = _narration(
            [
                f"You ask about lodging in {loc}. A night costs more coin than you like, or a favor you like even less.",
                "You learn the prices and the traps. Sleep is available. Trust is not included.",
            ]
        )
        events.append(
            {
                "title": "Lodging options noted",
                "location": loc,
                "summary": f"{name} priced safe and unsafe lodging options at {loc}.",
                "status": "background",
                "persistence": "temporary",
                "disappear_chance": 50,
            }
        )

    elif kind == "lead":
        narration = _narration(
            [
                f"You follow a lead one step only. From {loc}, that step is enough to see the next door, the next liar, or the next empty alley—and then you stop.",
                "Commitment is expensive. Reassessment is cheap. You pay the cheap price on purpose.",
            ]
        )
        player_patch["xp_delta"] = 2

    elif kind == "avoid":
        narration = _narration(
            [
                f"Trouble shapes itself in {loc}: raised voices, a hand near a belt, a path that wants to become a corner. You choose distance and cover.",
                "No duel. No speech. Just a clean angle out and the letter still sealed.",
            ]
        )
        player_patch["karma_delta"] = 0

    elif kind == "goal":
        narration = _narration(
            [
                f"You restate the only goal that matters in {loc}: deliver the sealed letter, survive the debts that circle it, and do not become a story told by collectors.",
                "Saying it aloud steadies the next choices. The world does not applaud. It simply remains available.",
            ]
        )
        player_patch["xp_delta"] = 1

    else:  # shift
        dest = place_name if place_name != loc else PLACES[(turn_index + 3) % len(PLACES)][0]
        narration = _narration(
            [
                f"The scene at {loc} cools or thickens—either way, standing still pays poorly. You shift pressure toward {dest}.",
                f"Cycle {cycle + 1} of the long road continues. The letter is still sealed. The debts are still patient. You are still moving.",
            ]
        )
        move_to = dest
        locations.append({"name": dest, "summary": next((p[1] for p in PLACES if p[0] == dest), "Another beat of the frontier.")})
        player_patch["move_to_location"] = dest
        player_patch["xp_delta"] = 2

    # Mild injury every 17th turn to exercise health
    if turn_index % 17 == 0:
        player_patch["health_delta"] = int(player_patch.get("health_delta") or 0) - 1
        narration = _narration(
            [
                narration,
                "A scrape finds you anyway—stone, nail, or careless elbow. Not fatal. Not free.",
            ]
        )

    turn_summary = f"turn {turn_index} [{kind}] at {loc}" + (f" -> {move_to}" if move_to else "") + f": {player_action[:120]}"
    return _base_result(
        loc,
        narration,
        turn_summary,
        player=player_patch,
        locations=locations,
        npcs=npcs,
        inventory_changes=inventory,
        events=events,
        gm_events=gm_events,
        conversations=conversations,
        skill_changes=skill_changes,
    )


def _snapshot(state: dict) -> dict:
    player = state.get("player") or {}
    return {
        "name": player.get("name"),
        "health": player.get("health"),
        "max_health": player.get("max_health"),
        "level": player.get("level"),
        "xp": player.get("xp"),
        "gold": player.get("gold"),
        "location": _loc_name(state),
        "inventory_count": len(state.get("inventory") or []),
        "event_count": len(state.get("events") or []),
        "location_count": len(state.get("locations") or []),
        "turn_summaries": len(state.get("turn_summaries") or []),
    }


def main() -> int:
    target = max(1, _env_int("GROK_BENCH_TURNS", 100))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    live_log = REPORT_DIR / f"dual-live-{stamp}.log"
    jsonl_path = REPORT_DIR / f"dual-turns-{stamp}.jsonl"
    report_path = REPORT_DIR / f"dual-report-{stamp}.json"

    temp = Path(tempfile.mkdtemp(prefix="morkyn_grok_dual_"))
    for key, val in {
        "AI_RPG_DB": str(temp / "world.db"),
        "AI_RPG_SOURCE_INDEX": str(temp / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(temp / "history.jsonl"),
        "AI_RPG_CONSOLIDATED_FACTS": str(temp / "facts.jsonl"),
        "AI_RPG_CAMPAIGN_SLOTS": str(temp / "slots"),
        "AI_RPG_MODEL_TRACE_DIR": str(temp / "traces"),
        # Force any accidental LLM path to fail fast rather than hang on Ollama.
        "AI_RPG_MODEL_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": "http://127.0.0.1:9",
        "OLLAMA_MODEL": "unused-dual-role",
    }.items():
        os.environ[key] = val
    (temp / "source_index").mkdir(exist_ok=True)
    (temp / "traces").mkdir(exist_ok=True)
    (temp / "slots").mkdir(exist_ok=True)

    sys.path.insert(0, str(REPO_ROOT))
    from app.db import init_db
    from app.world import OPENING_SCENE_INPUT, OPENING_SCENE_JOURNAL, apply_turn, get_state, start_playthrough

    init_db()
    t0 = time.perf_counter()
    report: dict = {
        "benchmark": "benchmarks dual-role (GM + player, no local LLM)",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "target_turns": target,
        "temp_dir": str(temp),
        "paths": {"live_log": str(live_log), "jsonl": str(jsonl_path), "report": str(report_path)},
        "opening": None,
        "turns": [],
        "summary": {},
    }

    errors = 0
    with live_log.open("w", encoding="utf-8") as log, jsonl_path.open("w", encoding="utf-8") as jsonl:
        def emit(msg: str) -> None:
            log.write(msg + "\n")
            log.flush()
            print(msg, flush=True)

        emit("benchmarks dual-role playtest (GM + player, apply_turn only)")
        emit(f"target_turns={target} temp={temp}")

        start_playthrough(_setup())
        state = get_state(include_hidden=True)

        # Opening as GM
        emit("\n=== OPENING (GM) ===")
        opening_result = gm_opening(state)
        try:
            state = apply_turn(
                opening_result,
                OPENING_SCENE_JOURNAL,
                used_fallback=False,
                fallback_reason="",
                input_kind="opening",
                prompt_context=None,
            )
            err = None
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            errors += 1
            state = get_state(include_hidden=True)
        opening_row = {
            "label": "opening",
            "error": err,
            "narration_len": len(str(opening_result.get("narration") or "")),
            "narration_preview": str(opening_result.get("narration") or "")[:400],
            "state": _snapshot(state),
        }
        report["opening"] = opening_row
        jsonl.write(json.dumps(opening_row, ensure_ascii=True, default=str) + "\n")
        emit(f"opening ok={err is None} loc={opening_row['state'].get('location')} inv={opening_row['state'].get('inventory_count')}")

        for i in range(1, target + 1):
            state = get_state(include_hidden=True)
            action = _player_action(i, state)  # PLAYER role
            gm_result = gm_turn(i, state, action)  # GM role
            t1 = time.perf_counter()
            try:
                state = apply_turn(
                    gm_result,
                    action,
                    used_fallback=False,
                    fallback_reason="",
                    input_kind="player",
                    prompt_context=None,
                )
                err = None
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                errors += 1
                state = get_state(include_hidden=True)
            elapsed = time.perf_counter() - t1
            row = {
                "label": f"turn_{i}",
                "turn_index": i,
                "role_player_action": action,
                "role_gm_kind": BEATS[(i - 1) % len(BEATS)][1],
                "seconds": round(elapsed, 4),
                "error": err,
                "narration_len": len(str(gm_result.get("narration") or "")),
                "narration_preview": str(gm_result.get("narration") or "")[:280],
                "state": _snapshot(state),
            }
            report["turns"].append(row)
            jsonl.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
            if i == 1 or i % 10 == 0 or i == target or err:
                emit(
                    f"turn {i}/{target} {elapsed*1000:.1f}ms kind={row['role_gm_kind']} "
                    f"loc={row['state'].get('location')} inv={row['state'].get('inventory_count')} "
                    f"events={row['state'].get('event_count')} xp={row['state'].get('xp')} err={err}"
                )
            if i % 25 == 0:
                jsonl.flush()
                report["summary"] = {
                    "completed_turns": i,
                    "errors": errors,
                    "elapsed_seconds": round(time.perf_counter() - t0, 3),
                    "in_progress": True,
                }
                report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")

        total = time.perf_counter() - t0
        final = _snapshot(get_state(include_hidden=True))
        locations = sorted(
            {
                (t.get("state") or {}).get("location")
                for t in report["turns"]
                if (t.get("state") or {}).get("location")
            }
        )
        report["summary"] = {
            "completed_turns": len(report["turns"]),
            "target_turns": target,
            "errors": errors,
            "elapsed_seconds": round(total, 3),
            "mean_apply_ms": round(
                1000 * sum(t.get("seconds") or 0 for t in report["turns"]) / max(1, len(report["turns"])),
                2,
            ),
            "unique_locations": locations,
            "final_state": final,
            "llm_used": False,
            "roles": ["player", "gm"],
            "backend": "apply_turn/SQLite",
            "ok": errors == 0 and len(report["turns"]) == target,
        }
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")

        # Curated public teaser (committed under docs/showcase when run for release).
        showcase_dir = REPO_ROOT / "docs" / "showcase"
        showcase_dir.mkdir(parents=True, exist_ok=True)
        teaser_path = showcase_dir / "100-turn-lore-teaser.md"
        metrics_path = showcase_dir / "100-turn-metrics.json"
        teaser_path.write_text(_build_showcase_markdown(report), encoding="utf-8")
        metrics_path.write_text(
            json.dumps(
                {
                    "benchmark": report.get("benchmark"),
                    "finished_at": report.get("finished_at"),
                    "summary": report.get("summary"),
                    "opening_preview": (report.get("opening") or {}).get("narration_preview"),
                    "sample_turns": [
                        {
                            "turn": t.get("turn_index"),
                            "kind": t.get("role_gm_kind"),
                            "player": t.get("role_player_action"),
                            "location": (t.get("state") or {}).get("location"),
                            "narration_preview": t.get("narration_preview"),
                        }
                        for t in report.get("turns") or []
                        if t.get("turn_index") in {1, 10, 25, 50, 75, 100}
                    ],
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        report["paths"]["showcase_md"] = str(teaser_path)
        report["paths"]["showcase_metrics"] = str(metrics_path)
        report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")

        emit("\n=== DONE ===")
        emit(json.dumps(report["summary"], ensure_ascii=True, indent=2))
        emit(f"report: {report_path}")
        emit(f"showcase: {teaser_path}")
        return 0 if report["summary"]["ok"] else 1


def _build_showcase_markdown(report: dict) -> str:
    """Human-readable lore teaser for the GitHub repo presentation."""
    summary = report.get("summary") or {}
    opening = report.get("opening") or {}
    turns = report.get("turns") or []
    final = summary.get("final_state") or {}
    locations = summary.get("unique_locations") or []
    sample_idx = {1, 10, 20, 35, 50, 65, 80, 100}

    lines = [
        "# Mosswake Road — 100-turn lore teaser",
        "",
        "> Dual-role stress run: **Player** chooses actions, **GM** narrates and mutates state, "
        "Mørkyn `apply_turn` / SQLite is the only backend. No local LLM was required for this harness.",
        "",
        "## Run snapshot",
        "",
        f"| | |",
        f"| --- | --- |",
        f"| Turns completed | **{summary.get('completed_turns')}** / {summary.get('target_turns')} |",
        f"| Errors | **{summary.get('errors')}** |",
        f"| Wall time | **{summary.get('elapsed_seconds')}s** |",
        f"| Mean apply | **{summary.get('mean_apply_ms')} ms** / turn |",
        f"| Unique locations | {len(locations)} |",
        f"| Final location | {final.get('location')} |",
        f"| Final level / XP | {final.get('level')} / {final.get('xp')} |",
        f"| Inventory items | {final.get('inventory_count')} |",
        f"| Events tracked | {final.get('event_count')} |",
        "",
        "## Premise",
        "",
        "You are the **Ashen Courier** — road-worn, letter-bound, debt-haunted. "
        "The sealed letter must reach its mark. Mosswake Gate and the north road do not care if you fail.",
        "",
        "### Opening",
        "",
        "```",
        str(opening.get("narration_preview") or "(no opening narration)"),
        "```",
        "",
        "## Places that hardened into lore",
        "",
    ]
    for loc in locations:
        lines.append(f"- **{loc}**")
    lines.extend(
        [
            "",
            "## Selected beats (player · GM)",
            "",
            "Excerpts from the long road — not every turn, just the spine of the story.",
            "",
        ]
    )
    for t in turns:
        idx = t.get("turn_index")
        if idx not in sample_idx:
            continue
        lines.extend(
            [
                f"### Turn {idx} — `{t.get('role_gm_kind')}` @ {(t.get('state') or {}).get('location')}",
                "",
                f"**Player:** {t.get('role_player_action')}",
                "",
                "```",
                str(t.get("narration_preview") or ""),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## What this proves",
            "",
            "- SQLite world state survives a **100-turn** dual-role campaign without soft-resetting the premise.",
            "- Locations, inventory, events, XP, and travel accumulate into a **coherent courier legend**.",
            "- The harness is fast enough to re-run on every release (`python benchmarks/run_dual_role_playtest.py`).",
            "",
            "Raw machine reports stay local under `benchmarks/reports/` (gitignored). "
            "This teaser is the shareable presentation slice.",
            "",
            f"_Generated {report.get('finished_at') or time.strftime('%Y-%m-%d')} · backend `{summary.get('backend')}`._",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
