"""Per-location body health: wounds, engine-owned healing states, treatments, capability effects.

Status: built, not wired (TODO n23).

The player's body is a fixed set of locations (head, torso, left and right arm, left and right hand,
left and right leg). A wound is a row on one location with a kind (cut, pierce, blunt, burn, bite), a
damage amount, a severity 1..4 derived from damage against the location's share of max_health, and
exactly one basic state from BASIC_STATES: bleeding, open, bandaged, broken, splinted, infected, healing,
bruised. Each state is a data row that says what it does per world hour, what it rolls each world day,
what it blocks, which treatments move it where, and when it moves on by itself. Treatments (bandage,
splint, clean, salve, stitch) are engine facts: a bandage stops bleeding and does not heal. Modifier
states are free text the model may attach to a wound ("poultice of yarrow", "stitched badly"); they are
stored, shown in prose lines and never read by a rule, and they cannot name or negate a basic state.
Capability effects (two-handed work, climbing, fine work, travel speed, combat penalties) come from a
table over location, state and severity. The aggregate health_from_body() maps the body to the single
player.health number, and wounds_from_health_delta() maps a health delta back into wounds, so the model
can run beside HP. All rule functions are pure over the Body dict; the writers touch only the module's
own tables body_wounds and body_health_log. The live game does not call anything here.

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

Tests: tests/test_body_health.py
"""
from __future__ import annotations

import copy
import json
import math
import random
import re
from typing import Any

from app.player_resources import _float, _int, world_abs_minutes
from app.prose_state import strip_negated_clauses

# ---------------------------------------------------------------------------
# Rules tables (data). Reshape numbers here; no code branch below hard-codes one.
# ---------------------------------------------------------------------------

# Locations: key -> (label, share of max_health in percent, hit weight when a delta names no location, group)
LOCATIONS = {
    "head":       ("head",       14, 10, "head"),
    "torso":      ("torso",      30, 36, "torso"),
    "left_arm":   ("left arm",   10, 12, "arm"),
    "right_arm":  ("right arm",  10, 12, "arm"),
    "left_hand":  ("left hand",   5,  4, "hand"),
    "right_hand": ("right hand",  5,  4, "hand"),
    "left_leg":   ("left leg",   13, 11, "leg"),
    "right_leg":  ("right leg",  13, 11, "leg"),
}                                            # shares sum to 100, hit weights sum to 100
VITAL_LOCATIONS = ("head", "torso")          # disabled -> incapacitated (aggregate health 0)
# Feet are folded into legs on purpose: the existing injury vocabulary has "hand" but no "foot", and feet
# add nothing to the capability table beyond what legs already carry. Adding them is a row here plus a
# LIMB_WORDS entry.

# Free limb words (skill_checks injuries, prose) -> location key or group; a group picks a side by rng.
LIMB_WORDS = {
    "head": "head", "skull": "head", "face": "head", "eye": "head", "jaw": "head", "ear": "head", "nose": "head", "scalp": "head",
    "torso": "torso", "chest": "torso", "side": "torso", "ribs": "torso", "rib": "torso", "back": "torso", "belly": "torso",
    "stomach": "torso", "gut": "torso", "shoulder": "arm", "arm": "arm", "elbow": "arm", "forearm": "arm", "wrist": "hand",
    "hand": "hand", "finger": "hand", "fingers": "hand", "thumb": "hand", "palm": "hand", "leg": "leg", "thigh": "leg",
    "knee": "leg", "shin": "leg", "calf": "leg", "ankle": "leg", "foot": "leg", "feet": "leg", "toe": "leg", "hip": "leg",
}
SIDE_WORDS = {"left": "left", "right": "right", "off": "left", "sword": "right", "main": "right"}
GROUPS = ("head", "torso", "arm", "hand", "leg")

# Severity from damage / location max_hp: (min_ratio, severity, label), scanned from the top.
SEVERITY_BY_RATIO = (
    (0.75, 4, "grave"),
    (0.45, 3, "serious"),
    (0.20, 2, "moderate"),
    (0.0,  1, "minor"),
)
SEVERITY_WORDS = {1: "mild", 2: "mild", 3: "serious", 4: "critical"}   # StatusLine severity by wound severity
MAX_WOUNDS_PER_LOCATION = 4            # a fifth merges its damage into the worst open wound there
DAMAGE_ZERO_EPS = 0.05                 # damage at or under this counts as zero (healed)

WOUND_KINDS = ("cut", "pierce", "blunt", "burn", "bite")
# Wound kinds -> the basic state a fresh wound starts in, by severity index 0..4 (index 0 unused).
KIND_START_STATE = {
    "cut":    (None, "bleeding", "bleeding", "bleeding", "bleeding"),
    "pierce": (None, "bleeding", "bleeding", "bleeding", "bleeding"),
    "bite":   (None, "open",     "bleeding", "bleeding", "bleeding"),
    "blunt":  (None, "bruised",  "bruised",  "broken",   "broken"),     # broken only on arm/hand/leg groups and torso(ribs); head blunt stays bruised
    "burn":   (None, "open",     "open",     "open",     "open"),
}
BREAKABLE_GROUPS = ("arm", "hand", "leg", "torso")
BLEEDING_KINDS = ("cut", "pierce", "bite")   # kinds whose healing wound can tear open again under strain

# Per-hour and per-day rule rows, indexed by severity 1..4 (index 0 = 0).
BLEED_PER_HOUR        = (0, 0.5, 1.5, 3.0, 5.0)     # health points lost per world hour while bleeding
BLEED_SELF_STOP_MIN   = (0, 60, 180, None, None)    # minutes after which bleeding stops on its own -> open; None = never
INFECT_LOSS_PER_HOUR  = (0, 0.1, 0.2, 0.35, 0.5)    # health points lost per hour while infected
INFECT_FATIGUE_PER_HR = (0, 0.25, 0.5, 0.75, 1.0)   # fever
INFECT_WORSEN_HOURS   = 24                          # untreated infection: severity +1 (max 4) every this many hours
HEAL_FRACTION_PER_HR  = (0, 0.008, 0.006, 0.0045, 0.003)   # share of location max_hp healed per hour at mult 1.0
                                                    # (sev1 ~25 h, sev2 ~75 h, sev3 ~170 h, sev4 ~330 h of rest)
MEND_HOURS            = (0, 48, 120, 240, 480)      # splinted -> healing after this long; damage then halves
INFECT_CHANCE_PER_DAY = {                           # rolled once per world day crossed, by severity
    "bleeding": (0, 0.05, 0.10, 0.15, 0.20),
    "open":     (0, 0.10, 0.20, 0.30, 0.40),
    "bandaged": (0, 0.02, 0.05, 0.08, 0.12),        # doubled when dressing_age_minutes > 1440
    "bruised": (0, 0, 0, 0, 0), "broken": (0, 0, 0, 0, 0), "splinted": (0, 0, 0, 0, 0),
    "healing": (0, 0.01, 0.02, 0.03, 0.04), "infected": (0, 0, 0, 0, 0),
}
DIRTY_DRESSING_MINUTES = 1440
CLOSED_AFTER_MINUTES = 1440                         # an open wound not infected for this long -> healing
REST_HEAL_MULT = {"none": 1.0, "wait": 1.1, "meditate": 1.2, "sleep": 1.6}
CARE_QUALITY_RANGE = (0.5, 1.5)
RECOVERY_MULT_FLOOR = 0.1
RECOVERY_MULT_CEIL = 1.25
LOSS_TABLES = {"BLEED_PER_HOUR": BLEED_PER_HOUR, "INFECT_LOSS_PER_HOUR": INFECT_LOSS_PER_HOUR,
               "INFECT_FATIGUE_PER_HR": INFECT_FATIGUE_PER_HR}

# The fixed set of basic states. Columns:
#   label; heal_mult (x HEAL_FRACTION_PER_HR; 0 = does not heal in this state);
#   loses_health (which per-hour table, or None); fatigue_table (or None); recovery_mult (what this
#   state does to the player's overall recovery; the worst open wound's value is used);
#   treatments: {treatment_key: next_state or "roll:<next_state>" for a chance-based treatment};
#   auto: list of (condition, next_state): "self_stop" (BLEED_SELF_STOP_MIN), "mended" (MEND_HOURS),
#   "damage_zero" (wound removed as healed), "closed_24h" (open wound not infected for 24 h -> healing);
#   blocks_note: the closing clause of the wound's status line.
BASIC_STATES = {
    "bleeding": {"label": "bleeding",  "heal_mult": 0.0, "loses_health": "BLEED_PER_HOUR",  "fatigue_table": None,
                 "recovery_mult": 0.8, "treatments": {"bandage": "bandaged", "stitch": "bandaged"},
                 "auto": (("self_stop", "open"),), "blocks_note": "the wound is still bleeding"},
    "open":     {"label": "open wound", "heal_mult": 0.4, "loses_health": None, "fatigue_table": None,
                 "recovery_mult": 0.95, "treatments": {"bandage": "bandaged", "stitch": "bandaged", "clean": "open", "salve": "open"},
                 "auto": (("closed_24h", "healing"), ("damage_zero", "healed")), "blocks_note": "it is not closed"},
    "bandaged": {"label": "bandaged",  "heal_mult": 0.8, "loses_health": None, "fatigue_table": None,
                 "recovery_mult": 1.0, "treatments": {"bandage": "bandaged", "clean": "bandaged", "salve": "bandaged"},
                 "auto": (("damage_zero", "healed"),), "blocks_note": "it is not healed"},
    "broken":   {"label": "broken",    "heal_mult": 0.0, "loses_health": None, "fatigue_table": None,
                 "recovery_mult": 0.9, "treatments": {"splint": "splinted"},
                 "auto": (), "blocks_note": "the bone is not set"},
    "splinted": {"label": "splinted",  "heal_mult": 0.5, "loses_health": None, "fatigue_table": None,
                 "recovery_mult": 1.0, "treatments": {"splint": "splinted"},
                 "auto": (("mended", "healing"),), "blocks_note": "the bone is set but not knit"},
    "infected": {"label": "infected",  "heal_mult": 0.0, "loses_health": "INFECT_LOSS_PER_HOUR", "fatigue_table": "INFECT_FATIGUE_PER_HR",
                 "recovery_mult": 0.7, "treatments": {"clean": "roll:healing", "salve": "roll:healing", "bandage": "infected"},
                 "auto": (), "blocks_note": "the wound is hot and weeping"},
    "healing":  {"label": "healing",   "heal_mult": 1.0, "loses_health": None, "fatigue_table": None,
                 "recovery_mult": 1.0, "treatments": {"bandage": "healing", "salve": "healing", "clean": "healing"},
                 "auto": (("damage_zero", "healed"),), "blocks_note": "it is closing"},
    "bruised":  {"label": "bruised",   "heal_mult": 1.5, "loses_health": None, "fatigue_table": None,
                 "recovery_mult": 1.0, "treatments": {"salve": "bruised"},
                 "auto": (("damage_zero", "healed"),), "blocks_note": "it aches"},
}
TERMINAL_STATE = "healed"               # not a row: the wound's status becomes "healed" and it leaves body.wounds

# The same tuple as app/needs.py (leaves do not import each other; each test pins the literal).
WATER_WORDS = ("water", "waterskin", "water skin", "canteen", "flask", "bottle", "skin", "gourd")

# Treatments. item_words find the item to use; consumes says whether one unit leaves the inventory;
# skill is the skill_checks code whose outcome a caller may turn into quality; base_quality is used when
# no quality is passed; clear_chance is for "roll:" transitions (x quality, clamped 0.05..0.95);
# care_quality_set says whether the wound's care_quality becomes the treatment quality.
TREATMENTS = {
    "bandage": {"label": "bandage", "item_words": ("bandage", "bandages", "dressing", "linen", "cloth strip", "strip of cloth", "gauze", "rag", "cloth"),
                "consumes": True,  "skill": "medicine", "base_quality": 1.0, "clear_chance": 0.0, "care_quality_set": True,
                "fallback_words": ("shirt", "cloak", "tunic", "scarf"), "fallback_quality": 0.6},   # tearing clothing: lower quality, consumes nothing
    "splint":  {"label": "splint",  "item_words": ("splint", "splints", "brace", "board", "stick", "staff", "branch", "stave"),
                "consumes": False, "skill": "medicine", "base_quality": 1.0, "clear_chance": 0.0, "care_quality_set": True,
                "fallback_words": (), "fallback_quality": 0.0},
    "clean":   {"label": "clean",   "item_words": WATER_WORDS + ("wine", "spirits", "whisky", "whiskey", "vinegar", "salt", "brandy"),
                "consumes": False, "skill": "medicine", "base_quality": 1.0, "clear_chance": 0.5, "care_quality_set": False,
                "fallback_words": (), "fallback_quality": 0.0},
    "salve":   {"label": "salve",   "item_words": ("salve", "ointment", "balm", "poultice", "unguent", "herbs", "yarrow", "honey", "moss", "comfrey", "medicine", "medical kit", "healer's kit", "first aid"),
                "consumes": True,  "skill": "medicine", "base_quality": 1.1, "clear_chance": 0.75, "care_quality_set": True,
                "fallback_words": (), "fallback_quality": 0.0},
    "stitch":  {"label": "stitch",  "item_words": ("needle", "thread", "sinew", "sutures", "suture", "gut string"),
                "consumes": False, "skill": "medicine", "base_quality": 1.2, "clear_chance": 0.0, "care_quality_set": True,
                "fallback_words": (), "fallback_quality": 0.0},
}
TREATMENT_INTENT_WORDS = {
    "bandage": ("bandage", "bind", "wrap", "dress the wound", "dress my", "tie off", "staunch", "stop the bleeding", "press on"),
    "splint":  ("splint", "set the bone", "set my", "brace", "immobilise", "immobilize"),
    "clean":   ("clean", "wash", "rinse", "flush", "pour water", "pour wine"),
    "salve":   ("salve", "ointment", "poultice", "apply the", "rub", "smear", "treat"),
    "stitch":  ("stitch", "sew", "suture", "close the cut"),
}
TREATMENT_INTENT_ORDER = ("stitch", "splint", "bandage", "clean", "salve")   # tie-break when two phrases start together
# Phrases that are ordinary speech on their own ("set my pack down", "press on down the road"): they count
# only when a LIMB_WORDS word follows within this many words.
LIMB_BOUND_PHRASES = ("set my", "press on")
LIMB_BOUND_WINDOW = 3
MIN_SEVERITY_FOR_STITCH = 2             # a stitch on a minor cut is just a bandage
CLEAR_CHANCE_RANGE = (0.05, 0.95)
# Same-state table entries that are not a re-dress but do nothing: (treatment, state) -> ok False, reason no_effect.
NO_EFFECT = {("bandage", "infected")}
# Item types whose description counts for word matching (0.6 of the design); blank counts too.
DESCRIPTION_ITEM_TYPES = ("consumable", "food", "drink", "provisions", "medical", "medicine", "kit", "supplies", "")

# Prose lines by (treatment, state reached); {loc} is the location label.
TREATMENT_LINES = {
    ("bandage", "bandaged"): "You bind the {loc}; the bleeding stops. The wound is not healed.",
    ("stitch", "bandaged"):  "You stitch the {loc} closed and bind it. The wound is not healed.",
    ("splint", "splinted"):  "You splint the {loc}; the bone is set, but it will take long to knit.",
    ("clean", "healing"):    "You clean the {loc}; the infection drains and the wound starts to mend.",
    ("salve", "healing"):    "The salve draws the heat out of the {loc}; the wound starts to mend.",
}
REDRESS_LINES = {           # same-state entries; {state} is the state label
    "bandage": "You bind the {loc} afresh; it is still {state}.",
    "splint":  "You check the splint on the {loc}; it is still {state}.",
    "clean":   "You wash the {loc}; it is still {state}.",
    "salve":   "You dress the {loc} with salve; it is still {state}.",
    "stitch":  "You check the stitches on the {loc}; it is still {state}.",
}
FAILED_ROLL_LINES = {
    "clean": "You wash the {loc}, but the infection holds.",
    "salve": "The salve does not take; the {loc} is still infected.",
}
NO_EFFECT_LINE = "Binding the {loc} does nothing for the infection; it needs cleaning."
NOT_APPLICABLE_LINE = "A {treatment} does nothing for a {kind} that is {state}."
GENERIC_TREATMENT_LINE = "You tend the {loc}; it is now {state}."

# Capability effects. Keys: (group, state or "*", min_severity) -> effects dict. Per wound, the state row
# that matches wins; otherwise the "*" row with the highest min_severity at or under the wound's severity
# applies; the group-less ("*", state) rows add on top. Across wounds string capabilities take the worst
# word (ok < hampered < blocked); travel multipliers multiply (floor TRAVEL_SPEED_FLOOR); check_mods and
# combat penalties add.
CAPABILITY_RULES = {
    ("arm",   "*",        2): {"two_handed": "hampered", "check_mods": {"athletics": -1, "melee": -1}},
    ("arm",   "*",        3): {"two_handed": "blocked",  "climbing": "hampered", "check_mods": {"athletics": -2, "melee": -2}, "combat": {"attack": -2}},
    ("arm",   "broken",   1): {"two_handed": "blocked",  "climbing": "hampered", "check_mods": {"athletics": -3, "melee": -2}, "combat": {"attack": -2, "defense": -1}},
    ("arm",   "splinted", 1): {"two_handed": "hampered", "climbing": "hampered", "check_mods": {"athletics": -2}},
    ("hand",  "*",        1): {"fine_work": "hampered",  "check_mods": {"craft": -1, "lockpicking": -1}},
    ("hand",  "*",        2): {"two_handed": "hampered", "fine_work": "hampered", "check_mods": {"craft": -2, "lockpicking": -2, "melee": -1}},
    ("hand",  "*",        3): {"two_handed": "blocked",  "fine_work": "blocked",  "check_mods": {"craft": -4, "lockpicking": -4, "melee": -2}, "combat": {"attack": -2}},
    ("hand",  "broken",   1): {"two_handed": "blocked",  "fine_work": "blocked",  "check_mods": {"craft": -4, "lockpicking": -4, "melee": -2}, "combat": {"attack": -2}},
    ("hand",  "splinted", 1): {"fine_work": "blocked",   "two_handed": "hampered", "check_mods": {"craft": -3, "lockpicking": -3}},
    ("leg",   "*",        1): {"travel_speed_mult": 0.9},
    ("leg",   "*",        2): {"travel_speed_mult": 0.75, "climbing": "hampered", "check_mods": {"athletics": -1}, "combat": {"mobility": -1}},
    ("leg",   "*",        3): {"travel_speed_mult": 0.6,  "climbing": "hampered", "check_mods": {"athletics": -2}, "combat": {"mobility": -2, "defense": -1}},
    ("leg",   "*",        4): {"travel_speed_mult": 0.4,  "climbing": "blocked",  "check_mods": {"athletics": -4}, "combat": {"mobility": -3, "defense": -2}},
    ("leg",   "broken",   1): {"travel_speed_mult": 0.4,  "climbing": "blocked",  "check_mods": {"athletics": -4}, "combat": {"mobility": -3, "defense": -2}},
    ("leg",   "splinted", 1): {"travel_speed_mult": 0.6,  "climbing": "blocked",  "check_mods": {"athletics": -3}, "combat": {"mobility": -2}},
    ("torso", "*",        3): {"travel_speed_mult": 0.8,  "climbing": "hampered", "check_mods": {"athletics": -2}, "combat": {"attack": -1, "defense": -1}},
    ("torso", "broken",   1): {"travel_speed_mult": 0.8,  "two_handed": "hampered", "climbing": "hampered", "check_mods": {"athletics": -2}, "combat": {"attack": -1}},
    ("head",  "*",        2): {"fine_work": "hampered",  "check_mods": {"perception": -1}},
    ("head",  "*",        3): {"fine_work": "hampered",  "climbing": "hampered", "check_mods": {"perception": -2, "athletics": -1}, "combat": {"defense": -1}},
    ("*",     "bleeding", 3): {"combat": {"attack": -1}},
    ("*",     "infected", 2): {"check_mods": {"athletics": -1}, "combat": {"attack": -1}},
}
TRAVEL_SPEED_FLOOR = 0.25
CAPABILITY_ORDER = ("ok", "hampered", "blocked")
CAPABILITY_WORDS = ("two_handed", "climbing", "fine_work")
CAPABILITY_PHRASES = {"two_handed": "use both hands", "climbing": "climb", "fine_work": "do fine work"}
COMBAT_KEYS = ("attack", "defense", "mobility")
BARELY_WALK_BELOW = 0.6                 # travel_speed_mult under this adds the "You can barely walk." line

# Strain: doing something a wound forbids. (activity, state, min_severity) -> {"chance", "to", "extra_damage_ratio"}.
# extra_damage_ratio is a share of location max_hp added to the wound; "to" is the state after (None keeps it).
STRAIN_RULES = {
    ("climb",      "broken",   1): {"chance": 1.0,  "to": None,       "extra_damage_ratio": 0.10},
    ("two_handed", "broken",   1): {"chance": 1.0,  "to": None,       "extra_damage_ratio": 0.08},
    ("fight",      "broken",   1): {"chance": 0.8,  "to": None,       "extra_damage_ratio": 0.10},
    ("travel",     "broken",   1): {"chance": 0.6,  "to": None,       "extra_damage_ratio": 0.05},   # legs only (group check in code)
    ("climb",      "splinted", 1): {"chance": 0.5,  "to": "broken",   "extra_damage_ratio": 0.05},
    ("fight",      "splinted", 1): {"chance": 0.5,  "to": "broken",   "extra_damage_ratio": 0.05},
    ("fight",      "bandaged", 2): {"chance": 0.35, "to": "bleeding", "extra_damage_ratio": 0.0},
    ("climb",      "bandaged", 2): {"chance": 0.35, "to": "bleeding", "extra_damage_ratio": 0.0},
    ("fight",      "healing",  2): {"chance": 0.25, "to": "bleeding", "extra_damage_ratio": 0.0},    # cut/pierce/bite only
    ("climb",      "healing",  2): {"chance": 0.25, "to": "bleeding", "extra_damage_ratio": 0.0},
}
STRAIN_ACTIVITIES = ("none", "travel", "climb", "fight", "two_handed", "fine_work", "work")
# Which locations an activity strains: climb -> arm, hand, leg, torso; two_handed -> arm, hand; travel -> leg, torso;
# fight -> all; fine_work -> hand; work -> arm, hand.
STRAIN_GROUPS = {"climb": ("arm", "hand", "leg", "torso"), "two_handed": ("arm", "hand"), "travel": ("leg", "torso"),
                 "fight": ("head", "torso", "arm", "hand", "leg"), "fine_work": ("hand",), "work": ("arm", "hand"), "none": ()}
STRAIN_LINES = {
    "climb": "Climbing with a {state} {loc} costs you dearly.",
    "two_handed": "Working two-handed with a {state} {loc} tears at it.",
    "fight": "Fighting on a {state} {loc} makes it worse.",
    "travel": "The road is hard on a {state} {loc}.",
}

# Modifier layer limits.
MAX_MODIFIERS_PER_WOUND = 3
MODIFIER_NAME_MAX = 60
MODIFIER_NOTE_MAX = 200
MODIFIER_FORBIDDEN_WORDS = tuple(BASIC_STATES) + ("healed", "cured", "mended", "closed", "stopped", "fixed", "gone", "removed", "no longer")
# A modifier may not be a basic state key, may not contain a negation of one ("not bleeding"), and may not
# claim a terminal outcome. "stitched badly", "poultice of yarrow", "swollen", "throbbing", "dirty" pass.

# Aggregate mapping.
AGGREGATE_MODE = "damage_sum"     # health = max_health - sum(open wound damage), 0 when a vital location is disabled
HEAL_DISTRIBUTION = "worst_first" # a positive health delta reduces the highest-damage wound first

# Check outcome word (skill_checks OUTCOME_RANK keys) -> treatment quality.
QUALITY_BY_OUTCOME = {"critical_success": 1.5, "success": 1.0, "partial": 0.8, "failure": 0.6, "critical_failure": 0.5}

# MoveVerdict reasons this module produces (contracts.md 1.9 registry).
MOVE_REASONS = ("incapacitated", "cannot_walk")
MOVE_MESSAGES = {
    "incapacitated": "You cannot move; your body will not answer. Someone must tend your wounds first.",
    "cannot_walk": "Both your legs have given out; you cannot walk. You can still act where you lie.",
}

# Event proposals (contracts.md 1.7): heavy bleeding that will not stop on its own.
EVENT_TRIGGER_BLEEDING = "body:bleeding"
EVENT_PRIORITY = 6
EVENT_MIN_SEVERITY = 3

PROMPT_HEADER = "Player body (server truth):"
PROMPT_RULE_LINE = "Treatments change states only as the engine says: a bandage stops bleeding, it does not heal."
STATUS_LINE_MAX = 160

_BODY_WOUNDS_SQL = """
CREATE TABLE IF NOT EXISTS body_wounds (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  location TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'cut',
  severity INTEGER NOT NULL DEFAULT 1,
  damage REAL NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'bleeding',
  state_since_abs INTEGER NOT NULL DEFAULT 0,
  dressing_age_minutes INTEGER NOT NULL DEFAULT 0,
  care_quality REAL NOT NULL DEFAULT 1.0,
  modifiers TEXT NOT NULL DEFAULT '[]',
  cause TEXT NOT NULL DEFAULT '',
  created_turn INTEGER NOT NULL DEFAULT 0,
  created_abs INTEGER NOT NULL DEFAULT 0,
  closed_turn INTEGER NOT NULL DEFAULT 0,
  closed_abs INTEGER,
  status TEXT NOT NULL DEFAULT 'open',
  loss_carry REAL NOT NULL DEFAULT 0,
  fatigue_carry REAL NOT NULL DEFAULT 0
)
"""
# loss_carry and fatigue_carry hold the fraction of a health loss or fever fatigue that the last tick did not
# charge, so ten 6-minute ticks cost the same whole points as one 60-minute tick (needs keeps its own carry).
_BODY_WOUNDS_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_body_wounds_status ON body_wounds (status, location)"
_BODY_HEALTH_LOG_SQL = """
CREATE TABLE IF NOT EXISTS body_health_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  turn INTEGER NOT NULL DEFAULT 0,
  abs_minute INTEGER NOT NULL DEFAULT 0,
  wound_id INTEGER,
  event TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT ''
)
"""
OWN_TABLES = ("body_wounds", "body_health_log")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _whole(value: float) -> int:
    """Round half away from zero, so -1.5 is -2 and 0.4 is 0."""
    return int(math.copysign(math.floor(abs(value) + 0.5), value))


def _field(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _norm_words(text: Any) -> str:
    return " " + re.sub(r"[^a-z0-9']+", " ", str(text or "").lower()).strip() + " "


def _word_in(text: Any, words: tuple) -> str:
    """The first word or phrase of words that appears whole in text, else ''."""
    hay = _norm_words(text)
    for word in words:
        if f" {word} " in hay:
            return word
    return ""


def _rng_for(rng: random.Random | None, abs_minute: int, salt: Any) -> random.Random:
    if rng is not None:
        return rng
    salt_int = _int(salt, 0) or 1
    return random.Random((int(abs_minute) * 1_000_003) ^ (salt_int * 7919))


def _label(location: str) -> str:
    return LOCATIONS[location][0]


def _group(location: str) -> str:
    return LOCATIONS[location][3]


def _state_label(state: str) -> str:
    row = BASIC_STATES.get(state)
    return row["label"] if row else state


def _check_location(location: str) -> str:
    if location not in LOCATIONS:
        raise ValueError(f"unknown body location: {location!r}")
    return location


def _check_kind(kind: str) -> str:
    if kind not in KIND_START_STATE:
        raise ValueError(f"unknown wound kind: {kind!r}")
    return kind


def _check_state(state: str) -> str:
    if state not in BASIC_STATES:
        raise ValueError(f"unknown wound state: {state!r}")
    return state


def _check_treatment(treatment: str) -> str:
    if treatment not in TREATMENTS:
        raise ValueError(f"unknown treatment: {treatment!r}")
    return treatment


def _copy_body(body: dict) -> dict:
    return copy.deepcopy(body)


def _find_wound(body: dict, wound_id: int | None) -> dict | None:
    """The open wound with that id; None id means the wound pick_wound would choose."""
    if wound_id is None:
        return pick_wound(body)
    for wound in body.get("wounds") or []:
        if wound.get("id") is not None and int(wound["id"]) == int(wound_id):
            return wound
    return None


def _mid_band_damage(severity: int, max_hp: int) -> float:
    severity = int(_clamp(int(severity), 1, 4))
    rows = sorted(SEVERITY_BY_RATIO, key=lambda r: r[0])
    for idx, (min_ratio, sev, _label_) in enumerate(rows):
        if sev == severity:
            next_min = rows[idx + 1][0] if idx + 1 < len(rows) else 1.0
            return (min_ratio + next_min) / 2.0 * max_hp
    return 0.1 * max_hp


# ---------------------------------------------------------------------------
# Shared shapes: PlayerDeltas, RecoveryModifier (identical bodies in app/needs.py)
# ---------------------------------------------------------------------------

def zero_deltas() -> dict[str, Any]:
    return {"energy": 0, "fatigue": 0, "health": 0, "energy_exact": 0.0, "fatigue_exact": 0.0, "health_exact": 0.0, "reasons": []}


def merge_deltas(a: dict, b: dict) -> dict[str, Any]:
    """Sum two PlayerDeltas: the six numbers add, the reasons concatenate. Identical body in needs."""
    a = a if isinstance(a, dict) else {}
    b = b if isinstance(b, dict) else {}
    out = zero_deltas()
    for key in ("energy", "fatigue", "health"):
        out[key] = _int(a.get(key), 0) + _int(b.get(key), 0)
        out[key + "_exact"] = _float(a.get(key + "_exact"), 0.0) + _float(b.get(key + "_exact"), 0.0)
    out["reasons"] = [str(r) for r in (a.get("reasons") or [])] + [str(r) for r in (b.get("reasons") or [])]
    return out


def _recovery_label(mult: float, factors: list[dict[str, Any]]) -> str:
    if abs(mult - 1.0) < 1e-9 or not factors:
        return ""
    words = []
    for f in factors:
        word = str(f.get("source") or "").replace("_", " ").replace(":", " ").strip()
        if word and word not in words:
            words.append(word)
    head = "recovery slowed" if mult < 1.0 else "recovery eased"
    return f"{head} ({', '.join(words)})"


def merge_recovery(a: dict, b: dict) -> dict[str, Any]:
    """Multiply two RecoveryModifiers, clamp 0.1..1.25, concatenate factors, rebuild the label. Identical body in needs."""
    a = a if isinstance(a, dict) else {}
    b = b if isinstance(b, dict) else {}
    mult = _clamp(_float(a.get("mult"), 1.0) * _float(b.get("mult"), 1.0), RECOVERY_MULT_FLOOR, RECOVERY_MULT_CEIL)
    factors = [dict(f) for f in (a.get("factors") or []) if isinstance(f, dict)] + [dict(f) for f in (b.get("factors") or []) if isinstance(f, dict)]
    return {"mult": mult, "factors": factors, "label": _recovery_label(mult, factors)}


# ---------------------------------------------------------------------------
# Body construction
# ---------------------------------------------------------------------------

def ensure_schema(conn) -> None:
    """Create body_wounds, its index and body_health_log when missing. One statement per execute; no commit."""
    conn.execute(_BODY_WOUNDS_SQL)
    conn.execute(_BODY_WOUNDS_INDEX_SQL)
    conn.execute(_BODY_HEALTH_LOG_SQL)


def _location_max_hp(max_health: int, key: str) -> int:
    share = LOCATIONS[key][1]
    return max(1, _whole(max(1, int(max_health)) * share / 100.0))


def new_body(max_health: int, *, abs_minute: int = 0) -> dict:
    max_health = max(1, _int(max_health, 1))
    locations = {}
    for key, (label, _share, _weight, _group_) in LOCATIONS.items():
        max_hp = _location_max_hp(max_health, key)
        locations[key] = {"key": key, "label": label, "max_hp": max_hp, "damage": 0.0, "hp": max_hp,
                          "wound_ids": [], "worst_severity": 0, "disabled": False}
    return {"max_health": max_health, "locations": locations, "wounds": [], "updated_abs": int(abs_minute)}


def _refresh_locations(out: dict) -> dict:
    """Recompute damage/hp/worst/disabled from out["wounds"] in place (the wound dicts keep their identity)."""
    max_health = max(1, _int(out.get("max_health"), 1))
    out["max_health"] = max_health
    locations = {}
    for key, (label, _share, _weight, _group_) in LOCATIONS.items():
        max_hp = _location_max_hp(max_health, key)
        locations[key] = {"key": key, "label": label, "max_hp": max_hp, "damage": 0.0, "hp": max_hp,
                          "wound_ids": [], "worst_severity": 0, "disabled": False}
    out["wounds"] = list(out.get("wounds") or [])
    for wound in out["wounds"]:
        loc = locations.get(wound.get("location"))
        if loc is None:
            continue
        loc["damage"] += max(0.0, _float(wound.get("damage"), 0.0))
        loc["wound_ids"].append(wound.get("id"))
        loc["worst_severity"] = max(loc["worst_severity"], _int(wound.get("severity"), 1))
    for loc in locations.values():
        loc["hp"] = max(0, loc["max_hp"] - _whole(loc["damage"]))
        loc["disabled"] = loc["hp"] <= 0
    out["locations"] = locations
    out.setdefault("updated_abs", 0)
    return out


def rebuild_locations(body: dict) -> dict:
    """A copy of body with damage/hp/worst/disabled recomputed from body.wounds."""
    return _refresh_locations(_copy_body(body))


def severity_for(damage: float, location_max_hp: int) -> tuple[int, str]:
    ratio = max(0.0, _float(damage, 0.0)) / max(1, int(location_max_hp))
    for min_ratio, severity, label in SEVERITY_BY_RATIO:
        if ratio >= min_ratio - 1e-9:
            return severity, label
    return 1, SEVERITY_BY_RATIO[-1][2]


def severity_label(severity: int) -> str:
    for _min_ratio, sev, label in SEVERITY_BY_RATIO:
        if sev == int(severity):
            return label
    return SEVERITY_BY_RATIO[-1][2]


def _side_in(text: str) -> str:
    for word in _norm_words(text).split():
        if word in SIDE_WORDS:
            return SIDE_WORDS[word]
    return ""


def location_for(limb_word: str, *, side_hint: str = "", rng: random.Random | None = None) -> str:
    """A location key for a free limb word; a group picks a side; unknown words land on the torso."""
    text = str(limb_word or "").strip().lower()
    key = text.replace(" ", "_")
    if key in LOCATIONS:
        return key
    target = ""
    for word in _norm_words(text).split():
        if word in LIMB_WORDS:
            target = LIMB_WORDS[word]
            break
    if not target:
        return "torso"
    if target in LOCATIONS:
        return target
    side = SIDE_WORDS.get(str(side_hint or "").strip().lower(), "") or _side_in(text)
    if not side:
        roll = rng if rng is not None else random.Random(sum(ord(ch) for ch in text) or 1)
        side = roll.choice(("left", "right"))
    return f"{side}_{target}"


def roll_location(*, rng: random.Random | None = None, abs_minute: int = 0) -> str:
    roll = _rng_for(rng, abs_minute, 1)
    pick = roll.random() * 100.0
    total = 0.0
    for key, (_label_, _share, weight, _group_) in LOCATIONS.items():
        total += weight
        if pick < total:
            return key
    return "torso"


def _start_state(kind: str, severity: int, location: str) -> str:
    state = KIND_START_STATE[kind][int(_clamp(severity, 1, 4))]
    if state == "broken" and _group(location) not in BREAKABLE_GROUPS:
        return "bruised"
    return state


def _new_wound(location: str, kind: str, damage: float, severity: int, state: str, *, cause: str,
               turn: int, abs_minute: int) -> dict:
    return {
        "id": None, "location": location, "kind": kind, "severity": int(severity), "damage": float(damage),
        "state": state, "state_since_abs": int(abs_minute), "dressing_age_minutes": 0, "care_quality": 1.0,
        "modifiers": [], "cause": str(cause or "")[:120], "created_turn": int(turn), "created_abs": int(abs_minute),
        "closed_turn": 0, "closed_abs": None, "status": "open", "loss_carry": 0.0, "fatigue_carry": 0.0,
    }


def _resize(wound: dict, max_hp: int) -> None:
    wound["damage"] = max(0.0, _float(wound.get("damage"), 0.0))
    wound["severity"] = severity_for(wound["damage"], max_hp)[0]


def add_wound(body: dict, *, location: str, kind: str = "cut", damage: float | None = None, severity: int | None = None,
              cause: str = "", turn: int = 0, abs_minute: int = 0, state: str | None = None) -> tuple[dict, dict]:
    """A new open wound on location; over the per-location cap the damage merges into the worst wound there."""
    _check_location(location)
    _check_kind(kind)
    if damage is None and severity is None:
        raise ValueError("add_wound needs damage or severity")
    out = rebuild_locations(body)
    max_hp = out["locations"][location]["max_hp"]
    if damage is None:
        damage = _mid_band_damage(int(severity), max_hp)
    damage = max(0.0, _float(damage, 0.0))
    sev = severity_for(damage, max_hp)[0]
    open_here = [w for w in out["wounds"] if w.get("location") == location]
    if len(open_here) >= MAX_WOUNDS_PER_LOCATION:
        worst = max(open_here, key=lambda w: _float(w.get("damage"), 0.0))
        worst["damage"] = _float(worst.get("damage"), 0.0) + damage
        _resize(worst, max_hp)
        _refresh_locations(out)
        out["updated_abs"] = int(abs_minute)
        return out, worst
    if state is None:
        state = _start_state(kind, sev, location)
    else:
        _check_state(state)
    wound = _new_wound(location, kind, damage, sev, state, cause=cause, turn=turn, abs_minute=abs_minute)
    out["wounds"].append(wound)
    _refresh_locations(out)
    out["updated_abs"] = int(abs_minute)
    return out, wound


_BLUNT_SUMMARY_RE = re.compile(r"\bhurt\b", re.I)
_SHARP_SUMMARY_RE = re.compile(r"\b(?:cut|slash|slashed|stab|stabbed|pierce|pierced)\b", re.I)


def wounds_from_injury(body: dict, injury: dict, *, turn: int, abs_minute: int, rng: random.Random | None = None) -> tuple[dict, dict]:
    """A wound from skill_checks.resolve_check()["injury"]."""
    injury = injury if isinstance(injury, dict) else {}
    summary = str(injury.get("summary") or "")
    location = location_for(str(injury.get("limb") or ""), rng=rng)
    damage = max(0.5, -_float(injury.get("health_delta"), -1.0))
    kind = "blunt" if (_BLUNT_SUMMARY_RE.search(summary) and not _SHARP_SUMMARY_RE.search(summary)) else "cut"
    return add_wound(body, location=location, kind=kind, damage=damage, cause=summary[:120], turn=turn, abs_minute=abs_minute)


def wounds_from_health_delta(body: dict, health_delta: int, *, location: str | None = None, kind: str = "cut",
                             cause: str = "", turn: int = 0, abs_minute: int = 0,
                             rng: random.Random | None = None) -> tuple[dict, list[dict]]:
    """Negative: new wound(s) carrying -health_delta damage. Positive: heal worst-first. Zero: nothing."""
    delta = _int(health_delta, 0)
    if delta == 0:
        return _copy_body(body), []
    if delta < 0:
        damage = float(-delta)
        loc = location or roll_location(rng=rng, abs_minute=abs_minute)
        _check_location(loc)
        current = rebuild_locations(body)
        max_hp = current["locations"][loc]["max_hp"]
        remaining = max(0.0, max_hp - current["locations"][loc]["damage"])
        touched: list[dict] = []
        spill = 0.0
        local = damage
        if loc != "torso" and damage > 0.75 * max_hp:
            local = min(damage, remaining)
            spill = damage - local
        out = current
        if local > 0:
            out, wound = add_wound(out, location=loc, kind=kind, damage=local, cause=cause, turn=turn, abs_minute=abs_minute)
            touched.append(wound)
        if spill > 0:
            out, wound = add_wound(out, location="torso", kind=kind, damage=spill, cause=cause, turn=turn, abs_minute=abs_minute)
            touched.append(wound)
        return out, touched
    out = rebuild_locations(body)
    left = float(delta)
    touched = []
    for wound in sorted(out["wounds"], key=lambda w: -_float(w.get("damage"), 0.0)):
        if left <= 0:
            break
        take = min(left, _float(wound.get("damage"), 0.0))
        wound["damage"] = _float(wound.get("damage"), 0.0) - take
        left -= take
        _resize(wound, out["locations"][wound["location"]]["max_hp"])
        touched.append(wound)
    healed = [w for w in out["wounds"] if w["damage"] <= DAMAGE_ZERO_EPS]
    for wound in healed:
        _mark_healed(wound, turn=turn, abs_minute=abs_minute)
    out["wounds"] = [w for w in out["wounds"] if w["status"] == "open"]
    _refresh_locations(out)
    out["updated_abs"] = int(abs_minute)
    return out, touched


def _mark_healed(wound: dict, *, turn: int, abs_minute: int) -> None:
    wound["damage"] = 0.0
    wound["status"] = "healed"
    wound["closed_turn"] = int(turn)
    wound["closed_abs"] = int(abs_minute)


def health_from_body(body: dict) -> dict:
    current = rebuild_locations(body)
    max_health = current["max_health"]
    total = sum(_float(w.get("damage"), 0.0) for w in current["wounds"])
    disabled = [key for key, loc in current["locations"].items() if loc["disabled"]]
    incapacitated = any(key in VITAL_LOCATIONS for key in disabled)
    health = int(_clamp(_whole(max_health - total), 0, max_health))
    if incapacitated:
        health = 0
    worst = None
    if current["wounds"]:
        top = max(current["wounds"], key=lambda w: (_int(w.get("severity"), 1), _float(w.get("damage"), 0.0)))
        worst = {"location": top["location"], "severity": int(top["severity"]), "state": top["state"]}
    return {"health": health, "max_health": max_health, "ratio": health / max_health if max_health else 0.0,
            "incapacitated": incapacitated, "worst": worst, "disabled_locations": disabled}


# ---------------------------------------------------------------------------
# Treatments
# ---------------------------------------------------------------------------

def quality_from_outcome(outcome: str) -> float:
    return float(QUALITY_BY_OUTCOME.get(str(outcome or "").strip().lower(), 1.0))


def _treatment_result(ok: bool, reason: str, body: dict, wound: dict | None, from_state: str, to_state: str,
                      line: str, quality: float) -> dict:
    return {"ok": ok, "reason": reason, "body": body, "wound": wound, "from": from_state, "to": to_state,
            "line": line, "quality": float(quality)}


def apply_treatment(body: dict, wound_id: int | None, treatment: str, *, quality: float = 1.0, turn: int = 0,
                    abs_minute: int = 0, rng: random.Random | None = None) -> dict:
    """Move one wound along BASIC_STATES[state]["treatments"]; a bandage stops bleeding and heals nothing."""
    _check_treatment(treatment)
    out = rebuild_locations(body)
    wound = _find_wound(out, wound_id)
    quality = _clamp(_float(quality, 1.0), *CARE_QUALITY_RANGE)
    if wound is None:
        return _treatment_result(False, "no_such_wound", out, None, "", "", "There is no such wound to treat.", quality)
    used = treatment
    if treatment == "stitch" and _int(wound.get("severity"), 1) < MIN_SEVERITY_FOR_STITCH:
        used = "bandage"
    state = wound["state"]
    loc = _label(wound["location"])
    rule = TREATMENTS[used]
    entry = BASIC_STATES[state]["treatments"].get(used)
    if entry is None:
        line = NOT_APPLICABLE_LINE.format(treatment=rule["label"], kind=wound["kind"], state=_state_label(state))
        return _treatment_result(False, "not_applicable", out, wound, state, state, line, quality)
    if (used, state) in NO_EFFECT:
        return _treatment_result(False, "no_effect", out, wound, state, state, NO_EFFECT_LINE.format(loc=loc), quality)
    if entry.startswith("roll:"):
        to_state = _check_state(entry[5:])
        chance = _clamp(rule["clear_chance"] * quality, *CLEAR_CHANCE_RANGE)
        roll = _rng_for(rng, abs_minute, wound.get("id"))
        if roll.random() >= chance:
            wound["dressing_age_minutes"] = 0
            line = FAILED_ROLL_LINES.get(used, GENERIC_TREATMENT_LINE).format(loc=loc, state=_state_label(state))
            return _treatment_result(False, "failed_roll", out, wound, state, state, line, quality)
    else:
        to_state = _check_state(entry)
    wound["dressing_age_minutes"] = 0
    if rule["care_quality_set"]:
        wound["care_quality"] = quality
    if to_state == state:
        line = REDRESS_LINES.get(used, GENERIC_TREATMENT_LINE).format(loc=loc, state=_state_label(state))
        out["updated_abs"] = int(abs_minute)
        return _treatment_result(True, "", out, wound, state, state, line, quality)
    wound["state"] = to_state
    wound["state_since_abs"] = int(abs_minute)
    line = TREATMENT_LINES.get((used, to_state), GENERIC_TREATMENT_LINE).format(loc=loc, state=_state_label(to_state))
    out["updated_abs"] = int(abs_minute)
    return _treatment_result(True, "", out, wound, state, to_state, line, quality)


_QUOTE_SPLIT_RE = re.compile(r"[\"“”]")
_ITEM_HINT_RE = re.compile(r"\b(?:with|using)\s+(?:(?:a|an|the|some|my|this|that)\s+)?([^,.;!?\n]{1,60})", re.I)
_HINT_TRAIL_RE = re.compile(r"\s+(?:and|then|so|before|after|while)\b.*$", re.I)


def _unquoted(text: str) -> str:
    """The text outside double quotes (quoted speech is someone else's words)."""
    parts = _QUOTE_SPLIT_RE.split(str(text or ""))
    return " ".join(parts[0::2])


def _location_hint(text: str) -> str:
    words = _norm_words(text).split()
    for idx, word in enumerate(words):
        target = LIMB_WORDS.get(word)
        if not target:
            continue
        if target in LOCATIONS:
            return target
        side = SIDE_WORDS.get(words[idx - 1], "") if idx > 0 else ""
        return f"{side}_{target}" if side else target
    return ""


def _intent_position(text: str, words: tuple) -> int:
    """The earliest word index at which one of words starts in text, else -1; LIMB_BOUND_PHRASES need a limb word close behind."""
    tokens = _norm_words(text).split()
    best = -1
    for phrase in words:
        parts = phrase.split()
        for idx in range(len(tokens) - len(parts) + 1):
            if tokens[idx:idx + len(parts)] != parts:
                continue
            after = tokens[idx + len(parts):idx + len(parts) + LIMB_BOUND_WINDOW]
            if phrase in LIMB_BOUND_PHRASES and not any(word in LIMB_WORDS for word in after):
                continue
            if best < 0 or idx < best:
                best = idx
            break
    return best


def detect_treatment(player_input: str) -> dict:
    """{"treatment", "location_hint", "item_hint"} from the player's own words; quoted or denied lines count for nothing.

    The treatment phrase that appears earliest in the line wins; TREATMENT_INTENT_ORDER only breaks ties.
    """
    text = strip_negated_clauses(_unquoted(player_input))
    found = None
    found_at = -1
    for key in TREATMENT_INTENT_ORDER:
        pos = _intent_position(text, TREATMENT_INTENT_WORDS[key])
        if pos >= 0 and (found is None or pos < found_at):
            found, found_at = key, pos
    if found is None:
        return {"treatment": None, "location_hint": "", "item_hint": ""}
    item_hint = ""
    match = _ITEM_HINT_RE.search(text)
    if match:
        item_hint = _HINT_TRAIL_RE.sub("", match.group(1)).strip().rstrip(".,;")[:60]
    return {"treatment": found, "location_hint": _location_hint(text), "item_hint": item_hint}


def _row_matches(row: Any, words: tuple) -> bool:
    if _word_in(_field(row, "name", ""), words):
        return True
    item_type = str(_field(row, "item_type", "") or "").strip().lower()
    if _word_in(item_type, words):
        return True
    if item_type in DESCRIPTION_ITEM_TYPES and _word_in(_field(row, "description", ""), words):
        return True
    return False


def find_treatment_item(rows, treatment: str) -> tuple[Any, float, bool]:
    """(row, quality, consumes): the first stocked row the treatment's words name, else a fallback, else (None, 0.0, False)."""
    _check_treatment(treatment)
    rule = TREATMENTS[treatment]
    stocked = [row for row in (rows or []) if _int(_field(row, "quantity", 0), 0) > 0]
    for row in stocked:
        if _row_matches(row, rule["item_words"]):
            return row, float(rule["base_quality"]), bool(rule["consumes"])
    if rule["fallback_words"]:
        for row in stocked:
            if _row_matches(row, rule["fallback_words"]):
                return row, float(rule["fallback_quality"]), False
    return None, 0.0, False


def pick_wound(body: dict, *, location_hint: str = "", treatment: str | None = None) -> dict | None:
    """The open wound a hint and a treatment point at: hinted, treatable, worst, bleeding first."""
    wounds = list(body.get("wounds") or [])
    hint = str(location_hint or "").strip().lower().replace(" ", "_")
    if hint:
        if hint in LOCATIONS:
            wounds = [w for w in wounds if w.get("location") == hint]
        elif hint in GROUPS:
            wounds = [w for w in wounds if _group(w["location"]) == hint]
    if not wounds:
        return None

    def rank(wound: dict) -> tuple:
        applicable = 1 if treatment and treatment in BASIC_STATES[wound["state"]]["treatments"] else 0
        return (applicable, _int(wound.get("severity"), 1), 1 if wound["state"] == "bleeding" else 0, _float(wound.get("damage"), 0.0))

    return max(wounds, key=rank)


# ---------------------------------------------------------------------------
# Modifier layer
# ---------------------------------------------------------------------------

def _modifier_result(ok: bool, reason: str, body: dict, modifier: dict | None) -> dict:
    return {"ok": ok, "reason": reason, "body": body, "modifier": modifier}


def add_modifier(body: dict, wound_id: int | None, name: str, *, note: str = "", turn: int = 0) -> dict:
    """Attach a descriptive modifier to a wound; it can neither name nor undo a basic state."""
    out = _copy_body(body)
    wound = _find_wound(out, wound_id)
    if wound is None:
        return _modifier_result(False, "no_such_wound", out, None)
    clean = re.sub(r"\s+", " ", str(name or "")).strip()[:MODIFIER_NAME_MAX]
    if not clean:
        return _modifier_result(False, "empty", out, None)
    if _word_in(clean, MODIFIER_FORBIDDEN_WORDS):
        return _modifier_result(False, "forbidden_word", out, None)
    existing = wound.setdefault("modifiers", [])
    if any(str(m.get("name") or "").lower() == clean.lower() for m in existing):
        return _modifier_result(False, "duplicate", out, None)
    if len(existing) >= MAX_MODIFIERS_PER_WOUND:
        return _modifier_result(False, "too_many", out, None)
    modifier = {"name": clean, "note": str(note or "").strip()[:MODIFIER_NOTE_MAX], "refines": wound["state"], "added_turn": int(turn)}
    existing.append(modifier)
    return _modifier_result(True, "", out, modifier)


def remove_modifier(body: dict, wound_id: int | None, name: str) -> dict:
    out = _copy_body(body)
    wound = _find_wound(out, wound_id)
    if wound is None:
        return _modifier_result(False, "no_such_wound", out, None)
    target = str(name or "").strip().lower()
    for modifier in list(wound.get("modifiers") or []):
        if str(modifier.get("name") or "").lower() == target:
            wound["modifiers"].remove(modifier)
            return _modifier_result(True, "", out, modifier)
    return _modifier_result(False, "not_found", out, None)


# ---------------------------------------------------------------------------
# Time: strain and tick
# ---------------------------------------------------------------------------

def _transition(wound: dict, to_state: str, reason: str) -> dict:
    return {"wound_id": wound.get("id"), "location": wound["location"], "from": wound["state"], "to": to_state, "reason": reason}


def strain(body: dict, activity: str, *, abs_minute: int = 0, rng: random.Random | None = None) -> dict:
    """Apply STRAIN_RULES for one activity; unknown activity or "none" changes nothing."""
    out = rebuild_locations(body)
    groups = STRAIN_GROUPS.get(str(activity or "none"), ())
    transitions: list[dict] = []
    worsened: list[dict] = []
    lines: list[str] = []
    if not groups:
        return {"body": out, "transitions": transitions, "worsened": worsened, "lines": lines}
    for wound in out["wounds"]:
        group = _group(wound["location"])
        if group not in groups:
            continue
        for (act, state, min_sev), rule in STRAIN_RULES.items():
            if act != activity or wound["state"] != state or _int(wound.get("severity"), 1) < min_sev:
                continue
            if act == "travel" and state == "broken" and group != "leg":
                continue
            if state == "healing" and wound["kind"] not in BLEEDING_KINDS:
                continue
            roll = _rng_for(rng, abs_minute, wound.get("id"))
            if roll.random() >= rule["chance"]:
                continue
            max_hp = out["locations"][wound["location"]]["max_hp"]
            before_state = wound["state"]
            wound["damage"] = _float(wound.get("damage"), 0.0) + rule["extra_damage_ratio"] * max_hp
            _resize(wound, max_hp)
            to_state = rule["to"] or before_state
            transitions.append(_transition(wound, to_state, "strain"))
            if rule["to"]:
                wound["state"] = rule["to"]
                wound["state_since_abs"] = int(abs_minute)
                wound["dressing_age_minutes"] = 0
            worsened.append(wound)
            lines.append(STRAIN_LINES.get(act, "The {state} {loc} suffers for it.").format(
                state=_state_label(before_state), loc=_label(wound["location"])))
            break
    _refresh_locations(out)
    out["updated_abs"] = int(abs_minute)
    return {"body": out, "transitions": transitions, "worsened": worsened, "lines": lines}


def tick(body: dict, *, minutes: int, abs_minute: int, rest_kind: str = "none", recovery_mult: float = 1.0,
         activity: str = "none", rng: random.Random | None = None) -> dict:
    """Run every open wound's state rules over minutes ending at abs_minute. Losses are deltas, never wound damage."""
    minutes = _int(minutes, 0)
    out = rebuild_locations(body)
    deltas = zero_deltas()
    transitions: list[dict] = []
    healed: list[dict] = []
    if minutes <= 0:
        return {"body": out, "deltas": deltas, "transitions": transitions, "healed": healed, "lines": status_lines(out),
                "health": health_from_body(out), "hours": 0.0, "minutes": 0}
    abs_minute = int(abs_minute)
    abs_before = abs_minute - minutes
    hours = minutes / 60.0
    if activity and activity != "none":
        strained = strain(out, activity, abs_minute=abs_minute, rng=rng)
        out = strained["body"]
        transitions.extend(strained["transitions"])
    rest_mult = REST_HEAL_MULT.get(str(rest_kind or "none"), 1.0)
    recovery = _clamp(_float(recovery_mult, 1.0), RECOVERY_MULT_FLOOR, RECOVERY_MULT_CEIL)
    day_crossed = abs_before // 1440 != abs_minute // 1440
    for wound in out["wounds"]:
        max_hp = out["locations"][wound["location"]]["max_hp"]
        sev = int(_clamp(_int(wound.get("severity"), 1), 1, 4))
        rule = BASIC_STATES[wound["state"]]
        age_before = _int(wound.get("dressing_age_minutes"), 0)
        # 1. losses to the body; the wound keeps the fraction the whole-point delta does not charge this tick
        if rule["loses_health"]:
            loss = LOSS_TABLES[rule["loses_health"]][sev] * hours
            exact = loss + _float(wound.get("loss_carry"), 0.0)
            whole = _whole(exact)
            wound["loss_carry"] = exact - whole
            deltas["health_exact"] -= loss
            deltas["health"] -= whole
            deltas["reasons"].append(f"{wound['state']}:{wound['location']}")
        if rule["fatigue_table"]:
            gain = LOSS_TABLES[rule["fatigue_table"]][sev] * hours
            exact = gain + _float(wound.get("fatigue_carry"), 0.0)
            whole = _whole(exact)
            wound["fatigue_carry"] = exact - whole
            deltas["fatigue_exact"] += gain
            deltas["fatigue"] += whole
            deltas["reasons"].append(f"fever:{wound['location']}")
        # 2. healing
        if rule["heal_mult"] > 0:
            heal = max_hp * HEAL_FRACTION_PER_HR[sev] * rule["heal_mult"] * rest_mult * _float(wound.get("care_quality"), 1.0) * recovery * hours
            wound["damage"] = max(0.0, _float(wound.get("damage"), 0.0) - heal)
            _resize(wound, max_hp)
        # 3. auto transitions
        for condition, next_state in rule["auto"]:
            since = abs_minute - _int(wound.get("state_since_abs"), 0)
            fired = False
            if condition == "self_stop":
                limit = BLEED_SELF_STOP_MIN[sev]
                fired = limit is not None and since >= limit
            elif condition == "closed_24h":
                fired = since >= CLOSED_AFTER_MINUTES
            elif condition == "mended":
                fired = since >= MEND_HOURS[sev] * 60
            elif condition == "damage_zero":
                fired = wound["damage"] <= DAMAGE_ZERO_EPS
            if not fired:
                continue
            if next_state == TERMINAL_STATE:
                transitions.append(_transition(wound, TERMINAL_STATE, "healed"))
                _mark_healed(wound, turn=0, abs_minute=abs_minute)
                break
            transitions.append(_transition(wound, next_state, condition))
            if condition == "mended":
                wound["damage"] = wound["damage"] / 2.0
                _resize(wound, max_hp)
            wound["state"] = next_state
            wound["state_since_abs"] = abs_minute
            wound["dressing_age_minutes"] = 0
            break
        if wound["status"] != "open":
            healed.append(wound)
            continue
        # 4. the daily infection roll and the untreated infection worsening
        if day_crossed:
            chance = INFECT_CHANCE_PER_DAY.get(wound["state"], (0, 0, 0, 0, 0))[int(_clamp(wound["severity"], 1, 4))]
            if wound["state"] == "bandaged" and age_before > DIRTY_DRESSING_MINUTES:
                chance *= 2
            if chance > 0:
                roll = _rng_for(rng, abs_minute, wound.get("id"))
                if roll.random() < chance:
                    transitions.append(_transition(wound, "infected", "infected"))
                    wound["state"] = "infected"
                    wound["state_since_abs"] = abs_minute
                    wound["dressing_age_minutes"] = 0
        if wound["state"] == "infected":
            since_abs = _int(wound.get("state_since_abs"), 0)
            step = INFECT_WORSEN_HOURS * 60
            crossed = max(0, (abs_minute - since_abs) // step) - max(0, (abs_before - since_abs) // step)
            for _ in range(crossed):
                if wound["severity"] >= 4:
                    break
                wound["severity"] = int(wound["severity"]) + 1
                wound["damage"] = _mid_band_damage(wound["severity"], max_hp)
                transitions.append(_transition(wound, "infected", "worsened"))
        # 5. dressing age
        if wound["state"] == "bandaged":
            wound["dressing_age_minutes"] = age_before + minutes
    out["wounds"] = [w for w in out["wounds"] if w["status"] == "open"]
    _refresh_locations(out)
    out["updated_abs"] = abs_minute
    return {"body": out, "deltas": deltas, "transitions": transitions, "healed": healed, "lines": status_lines(out),
            "health": health_from_body(out), "hours": hours, "minutes": minutes}


# ---------------------------------------------------------------------------
# Capabilities, recovery, movement
# ---------------------------------------------------------------------------

def _rows_for_wound(wound: dict) -> list[dict]:
    group = _group(wound["location"])
    sev = _int(wound.get("severity"), 1)
    state = wound["state"]
    rows: list[dict] = []
    state_row = None
    for (g, st, min_sev), effects in CAPABILITY_RULES.items():
        if g == group and st == state and sev >= min_sev:
            state_row = effects
    if state_row is not None:
        rows.append(state_row)
    else:
        best = None
        best_sev = 0
        for (g, st, min_sev), effects in CAPABILITY_RULES.items():
            if g == group and st == "*" and sev >= min_sev and min_sev >= best_sev:
                best, best_sev = effects, min_sev
        if best is not None:
            rows.append(best)
    for (g, st, min_sev), effects in CAPABILITY_RULES.items():
        if g == "*" and st == state and sev >= min_sev:
            rows.append(effects)
    return rows


def _worse(a: str, b: str) -> str:
    return a if CAPABILITY_ORDER.index(a) >= CAPABILITY_ORDER.index(b) else b


def _fold_rows(rows: list[dict], caps: dict) -> None:
    for effects in rows:
        for word in CAPABILITY_WORDS:
            if word in effects:
                caps[word] = _worse(caps[word], effects[word])
        if "travel_speed_mult" in effects:
            caps["travel_speed_mult"] *= float(effects["travel_speed_mult"])
        for skill, mod in (effects.get("check_mods") or {}).items():
            caps["check_mods"][skill] = caps["check_mods"].get(skill, 0) + int(mod)
        for key, mod in (effects.get("combat") or {}).items():
            caps["combat"][key] = caps["combat"].get(key, 0) + int(mod)


def _wound_reason(wound: dict) -> str:
    label = _label(wound["location"])
    if wound["state"] in ("broken", "splinted", "infected", "bleeding"):
        return f"{label} {_state_label(wound['state'])}"
    return f"{label} {severity_label(wound['severity'])} {wound['kind']}"


def _empty_capabilities() -> dict:
    return {"two_handed": "ok", "climbing": "ok", "fine_work": "ok", "travel_speed_mult": 1.0, "check_mods": {},
            "combat": {key: 0 for key in COMBAT_KEYS}, "reasons": [], "blocked": []}


def capabilities(body: dict) -> dict:
    caps = _empty_capabilities()
    for wound in body.get("wounds") or []:
        rows = _rows_for_wound(wound)
        if rows:
            _fold_rows(rows, caps)
            caps["reasons"].append(_wound_reason(wound))
    caps["travel_speed_mult"] = round(max(TRAVEL_SPEED_FLOOR, caps["travel_speed_mult"]), 6)
    caps["blocked"] = [word for word in CAPABILITY_WORDS if caps[word] == "blocked"]
    return caps


def recovery_mult_from_body(body: dict) -> float:
    mults = [BASIC_STATES[w["state"]]["recovery_mult"] for w in (body.get("wounds") or []) if w.get("state") in BASIC_STATES]
    return float(min(mults)) if mults else 1.0


def recovery_modifier(body: dict) -> dict:
    mult = _clamp(recovery_mult_from_body(body), RECOVERY_MULT_FLOOR, RECOVERY_MULT_CEIL)
    factors = []
    for wound in body.get("wounds") or []:
        state_mult = BASIC_STATES.get(wound.get("state"), {}).get("recovery_mult", 1.0)
        if abs(state_mult - 1.0) > 1e-9:
            factors.append({"source": f"wound:{wound['location']}", "band": wound["state"], "mult": float(state_mult)})
    return {"mult": mult, "factors": factors, "label": _recovery_label(mult, factors)}


def move_verdict(body: dict, kind: str) -> dict:
    """contracts.md 1.9 MoveVerdict: refuse only when incapacitated or when both legs have given out."""
    reason = ""
    try:
        view = health_from_body(body)
        current = rebuild_locations(body)
        if view["incapacitated"]:
            reason = "incapacitated"
        elif current["locations"]["left_leg"]["disabled"] and current["locations"]["right_leg"]["disabled"]:
            reason = "cannot_walk"
    except Exception:
        reason = ""
    allowed = reason == ""
    return {"allowed": allowed, "reason": reason, "message": MOVE_MESSAGES.get(reason, "")[:160], "label": "",
            "kind": str(kind or ""), "movement_locked": not allowed}


# ---------------------------------------------------------------------------
# Prose and views
# ---------------------------------------------------------------------------

def _wound_line(wound: dict) -> str:
    mods = ", ".join(str(m.get("name") or "") for m in (wound.get("modifiers") or []) if m.get("name"))
    tail = BASIC_STATES[wound["state"]]["blocks_note"] or "it is not healed"
    mods_text = f" ({mods})" if mods else ""
    line = f"Your {_label(wound['location'])} has a {severity_label(wound['severity'])} {wound['kind']}, {_state_label(wound['state'])}{mods_text}; {tail}."
    return line[:STATUS_LINE_MAX]


def status_lines(body: dict) -> list[dict]:
    wounds = list(body.get("wounds") or [])
    if not wounds:
        return []
    lines = []
    for wound in wounds:
        sev = int(_clamp(_int(wound.get("severity"), 1), 1, 4))
        lines.append({"key": f"wound:{wound['location']}:{sev}", "severity": SEVERITY_WORDS[sev], "line": _wound_line(wound), "blocks": []})
    caps = capabilities(body)
    for word in CAPABILITY_WORDS:
        level = caps[word]
        if level == "ok":
            continue
        phrase = CAPABILITY_PHRASES[word]
        if level == "blocked":
            line, severity, blocks = f"You cannot {phrase} right now.", "serious", [word]
        else:
            line, severity, blocks = f"It is hard for you to {phrase} right now.", "mild", []
        lines.append({"key": f"capability:{word}", "severity": severity, "line": line[:STATUS_LINE_MAX], "blocks": blocks})
    if caps["travel_speed_mult"] < BARELY_WALK_BELOW:
        lines.append({"key": "travel", "severity": "serious", "line": "You can barely walk.", "blocks": []})
    return lines


def _health_summary(body: dict) -> str:
    parts = []
    for wound in sorted(body.get("wounds") or [], key=lambda w: -_int(w.get("severity"), 1)):
        parts.append(f"{_label(wound['location'])} {severity_label(wound['severity'])}")
    return ", ".join(parts)


def prompt_block(body: dict) -> str:
    lines = status_lines(body)
    if not lines:
        return ""
    view = health_from_body(body)
    out = [PROMPT_HEADER, f"- Health: {view['health']}/{view['max_health']} (body: {_health_summary(body)})"]
    out.extend(f"- {line['line']}" for line in lines)
    out.append(f"- {PROMPT_RULE_LINE}")
    return "\n".join(out)


def conditions_view(body: dict, *, turn: int = 0) -> list[dict]:
    """Entries in the legacy settings.player_conditions shape, one per open wound."""
    out = []
    for idx, wound in enumerate(body.get("wounds") or [], start=1):
        caps = _empty_capabilities()
        _fold_rows(_rows_for_wound(wound), caps)
        ident = wound.get("id") if wound.get("id") is not None else idx
        out.append({
            "id": f"wound_{ident}",
            "name": f"{_label(wound['location']).capitalize()}: {severity_label(wound['severity'])} {wound['kind']} ({_state_label(wound['state'])})",
            "summary": _wound_line(wound),
            "penalties": dict(caps["combat"]),
            "severe": _int(wound.get("severity"), 1) >= 3,
            "turn": int(turn),
        })
    return out


def state_view(body: dict) -> dict:
    current = rebuild_locations(body)
    locations = []
    for key, loc in current["locations"].items():
        states = [w["state"] for w in current["wounds"] if w["location"] == key]
        locations.append({"key": key, "label": loc["label"], "hp": loc["hp"], "max_hp": loc["max_hp"],
                          "worst_severity": loc["worst_severity"], "disabled": loc["disabled"], "states": states})
    wounds = []
    for wound in current["wounds"]:
        entry = dict(wound)
        entry["severity_label"] = severity_label(wound["severity"])
        entry["state_label"] = _state_label(wound["state"])
        wounds.append(entry)
    return {"max_health": current["max_health"], "health": health_from_body(current), "locations": locations,
            "wounds": wounds, "capabilities": capabilities(current), "lines": [line["line"] for line in status_lines(current)]}


def event_proposals(body: dict, *, turn: int) -> list[dict]:
    """contracts.md 1.7 WorldEventProposal rows for bleeding that will not stop by itself; never queued here."""
    out = []
    for wound in body.get("wounds") or []:
        sev = _int(wound.get("severity"), 1)
        if wound.get("state") != "bleeding" or sev < EVENT_MIN_SEVERITY:
            continue
        label = _label(wound["location"])
        out.append({
            "kind": "custom",
            "summary": f"Your {label} is still bleeding heavily; untreated it will cost you.",
            "trigger": EVENT_TRIGGER_BLEEDING,
            "due_turn": int(turn) + 1,
            "force": False,
            "priority": EVENT_PRIORITY,
            "payload": {"wound_id": wound.get("id"), "location": wound["location"], "severity": sev, "state": wound["state"]},
        })
    return out


# ---------------------------------------------------------------------------
# Writers: body_wounds and body_health_log only
# ---------------------------------------------------------------------------

def _row_values(wound: dict) -> tuple:
    return (
        wound["location"], wound["kind"], int(wound["severity"]), float(wound["damage"]), wound["state"],
        int(wound["state_since_abs"]), int(wound["dressing_age_minutes"]), float(wound["care_quality"]),
        json.dumps(list(wound.get("modifiers") or []), ensure_ascii=True), str(wound.get("cause") or "")[:120],
        int(wound["created_turn"]), int(wound["created_abs"]), int(wound["closed_turn"]),
        wound["closed_abs"] if wound.get("closed_abs") is None else int(wound["closed_abs"]), wound["status"],
        _float(wound.get("loss_carry"), 0.0), _float(wound.get("fatigue_carry"), 0.0),
    )


def _wound_from_row(row: Any) -> dict:
    try:
        modifiers = json.loads(_field(row, "modifiers", "[]") or "[]")
    except (TypeError, ValueError):
        modifiers = []
    closed_abs = _field(row, "closed_abs", None)
    return {
        "id": _int(_field(row, "id"), 0) or None,
        "location": str(_field(row, "location", "torso")),
        "kind": str(_field(row, "kind", "cut")),
        "severity": _int(_field(row, "severity"), 1),
        "damage": _float(_field(row, "damage"), 0.0),
        "state": str(_field(row, "state", "bleeding")),
        "state_since_abs": _int(_field(row, "state_since_abs"), 0),
        "dressing_age_minutes": _int(_field(row, "dressing_age_minutes"), 0),
        "care_quality": _float(_field(row, "care_quality"), 1.0),
        "modifiers": modifiers if isinstance(modifiers, list) else [],
        "cause": str(_field(row, "cause", "") or ""),
        "created_turn": _int(_field(row, "created_turn"), 0),
        "created_abs": _int(_field(row, "created_abs"), 0),
        "closed_turn": _int(_field(row, "closed_turn"), 0),
        "closed_abs": None if closed_abs is None else _int(closed_abs, 0),
        "status": str(_field(row, "status", "open")),
        "loss_carry": _float(_field(row, "loss_carry"), 0.0),
        "fatigue_carry": _float(_field(row, "fatigue_carry"), 0.0),
    }


LOG_DETAIL_MAX = 900
LOG_REASONS_MAX = 12


def _detail_json(event: str, detail: dict) -> str:
    """The detail as JSON that always parses: long reason lists are capped first, and a dump still over the limit is replaced."""
    detail = dict(detail or {})
    reasons = detail.get("reasons")
    if isinstance(reasons, list) and len(reasons) > LOG_REASONS_MAX:
        detail["reasons"] = [str(r) for r in reasons[:LOG_REASONS_MAX]] + [f"+{len(reasons) - LOG_REASONS_MAX} more"]
    text = json.dumps(detail, ensure_ascii=True)
    if len(text) > LOG_DETAIL_MAX:
        text = json.dumps({"truncated": True, "event": str(event)[:40]}, ensure_ascii=True)
    return text


def log_event(conn, *, turn: int, abs_minute: int, wound_id: int | None, event: str, detail: dict) -> None:
    conn.execute(
        "INSERT INTO body_health_log (turn, abs_minute, wound_id, event, detail) VALUES (?, ?, ?, ?, ?)",
        (int(turn), int(abs_minute), None if wound_id is None else int(wound_id), str(event)[:40],
         _detail_json(event, detail)),
    )


def load_body(conn, *, max_health: int, abs_minute: int = 0) -> dict:
    ensure_schema(conn)
    body = new_body(max_health, abs_minute=abs_minute)
    rows = conn.execute("SELECT * FROM body_wounds WHERE status = 'open' ORDER BY id").fetchall()
    body["wounds"] = [_wound_from_row(row) for row in rows]
    for wound in body["wounds"]:
        if wound["location"] not in LOCATIONS:
            wound["location"] = "torso"
        if wound["state"] not in BASIC_STATES:
            wound["state"] = "open"
    return rebuild_locations(body)


_INSERT_WOUND_SQL = """
INSERT INTO body_wounds (location, kind, severity, damage, state, state_since_abs, dressing_age_minutes,
                         care_quality, modifiers, cause, created_turn, created_abs, closed_turn, closed_abs, status,
                         loss_carry, fatigue_carry)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
_INSERT_WOUND_WITH_ID_SQL = """
INSERT INTO body_wounds (id, location, kind, severity, damage, state, state_since_abs, dressing_age_minutes,
                         care_quality, modifiers, cause, created_turn, created_abs, closed_turn, closed_abs, status,
                         loss_carry, fatigue_carry)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
_UPDATE_WOUND_SQL = """
UPDATE body_wounds
   SET location = ?, kind = ?, severity = ?, damage = ?, state = ?, state_since_abs = ?, dressing_age_minutes = ?,
       care_quality = ?, modifiers = ?, cause = ?, created_turn = ?, created_abs = ?, closed_turn = ?, closed_abs = ?, status = ?,
       loss_carry = ?, fatigue_carry = ?
 WHERE id = ?
"""


def _upsert_wound(conn, wound: dict) -> int:
    values = _row_values(wound)
    if wound.get("id") is None:
        cur = conn.execute(_INSERT_WOUND_SQL, values)
        return int(cur.lastrowid)
    cur = conn.execute(_UPDATE_WOUND_SQL, values + (int(wound["id"]),))
    if cur.rowcount == 0:
        conn.execute(_INSERT_WOUND_WITH_ID_SQL, (int(wound["id"]),) + values)
    return int(wound["id"])


def save_body(conn, body: dict, *, healed=(), turn: int = 0, abs_minute: int = 0) -> dict:
    """Upsert every open wound and mark healed ones; one log row per new and per healed wound."""
    ensure_schema(conn)
    out = rebuild_locations(body)
    for wound in out["wounds"]:
        was_new = wound.get("id") is None
        wound["id"] = _upsert_wound(conn, wound)
        if was_new:
            log_event(conn, turn=turn, abs_minute=abs_minute, wound_id=wound["id"], event="wound",
                      detail={"location": wound["location"], "kind": wound["kind"], "severity": wound["severity"],
                              "damage": round(wound["damage"], 3), "state": wound["state"], "cause": wound["cause"]})
    for wound in healed or ():
        if wound.get("status") != "healed":
            _mark_healed(wound, turn=turn, abs_minute=abs_minute)
        if not wound.get("closed_turn"):
            wound["closed_turn"] = int(turn)
        wound["id"] = _upsert_wound(conn, wound)
        log_event(conn, turn=turn, abs_minute=abs_minute, wound_id=wound["id"], event="healed",
                  detail={"location": wound["location"], "kind": wound["kind"]})
    _refresh_locations(out)
    return out


def tick_and_save(conn, *, minutes: int, world_time: dict, max_health: int, rest_kind: str = "none",
                  recovery_mult: float = 1.0, activity: str = "none", turn: int = 0) -> dict:
    abs_minute = world_abs_minutes(world_time)
    body = load_body(conn, max_health=max_health, abs_minute=abs_minute)
    result = tick(body, minutes=minutes, abs_minute=abs_minute, rest_kind=rest_kind, recovery_mult=recovery_mult, activity=activity)
    result["body"] = save_body(conn, result["body"], healed=result["healed"], turn=turn, abs_minute=abs_minute)
    for transition in result["transitions"]:
        if transition["reason"] == "healed":
            continue
        log_event(conn, turn=turn, abs_minute=abs_minute, wound_id=transition["wound_id"], event="transition", detail=transition)
    if result["deltas"]["health"] < 0:
        log_event(conn, turn=turn, abs_minute=abs_minute, wound_id=None, event="tick_loss",
                  detail={"health": result["deltas"]["health"], "health_exact": round(result["deltas"]["health_exact"], 3),
                          "fatigue": result["deltas"]["fatigue"], "reasons": result["deltas"]["reasons"], "minutes": minutes})
    return result


def treat_from_inventory(conn, intent: dict, *, rows, world_time: dict, max_health: int, turn: int = 0,
                         skill_quality: float | None = None) -> dict:
    """Pick the wound and the item, apply the treatment, persist on success; the consume is a proposal only."""
    abs_minute = world_abs_minutes(world_time)
    body = load_body(conn, max_health=max_health, abs_minute=abs_minute)
    treatment = (intent or {}).get("treatment")
    if not treatment or treatment not in TREATMENTS:
        result = _treatment_result(False, "not_applicable", body, None, "", "", "That is not a treatment you know.", 0.0)
        result["consume"] = None
        return result
    wound = pick_wound(body, location_hint=str((intent or {}).get("location_hint") or ""), treatment=treatment)
    if wound is None:
        result = _treatment_result(False, "no_such_wound", body, None, "", "", "There is no such wound to treat.", 0.0)
        result["consume"] = None
        return result
    row, item_quality, consumes = find_treatment_item(rows, treatment)
    if row is None:
        result = _treatment_result(False, "no_item", body, wound, wound["state"], wound["state"],
                                   f"You have nothing to {TREATMENTS[treatment]['label']} with.", 0.0)
        result["consume"] = None
        return result
    quality = item_quality * (_float(skill_quality, 1.0) if skill_quality is not None else 1.0)
    result = apply_treatment(body, wound["id"], treatment, quality=quality, turn=turn, abs_minute=abs_minute)
    result["consume"] = None
    if result["ok"]:
        result["body"] = save_body(conn, result["body"], turn=turn, abs_minute=abs_minute)
        log_event(conn, turn=turn, abs_minute=abs_minute, wound_id=wound["id"], event="treatment",
                  detail={"treatment": treatment, "from": result["from"], "to": result["to"], "quality": result["quality"],
                          "item": str(_field(row, "name", "") or "")})
        if consumes:
            result["consume"] = {"name": str(_field(row, "name", "") or ""), "quantity_delta": -1,
                                 "source": "body_health", "reason": treatment}
    return result


def add_modifier_and_save(conn, wound_id: int | None, name: str, *, note: str = "", turn: int = 0,
                          world_time: dict | None = None, max_health: int) -> dict:
    """add_modifier persisted; a None wound_id means the wound pick_wound would choose, as in add_modifier."""
    abs_minute = world_abs_minutes(world_time) if isinstance(world_time, dict) else 0
    body = load_body(conn, max_health=max_health, abs_minute=abs_minute)
    result = add_modifier(body, wound_id, name, note=note, turn=turn)
    if result["ok"]:
        wound = _find_wound(result["body"], wound_id)
        if wound is None or wound.get("id") is None:
            return _modifier_result(False, "no_such_wound", body, None)
        saved_id = int(wound["id"])
        conn.execute("UPDATE body_wounds SET modifiers = ? WHERE id = ?",
                     (json.dumps(list(wound.get("modifiers") or []), ensure_ascii=True), saved_id))
        log_event(conn, turn=turn, abs_minute=abs_minute, wound_id=saved_id, event="modifier",
                  detail={"name": result["modifier"]["name"], "refines": result["modifier"]["refines"]})
    return result
