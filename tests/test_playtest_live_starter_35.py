"""
Playtest #35 (live Qwen3 8B smoke run): gear, starter logic, ranks and fact titles.

Every string here is copied from the live smoke evidence (round 2 = the
player's launcher env, round 1 = without it):

  R2 g2 turn 1: the paragraph writer was offered every inventory row as
    "item the player carries" on every beat, and put the player's work gloves
    on the nurse Whitney Garcia; the R2 g1 opening put the player's
    mag-soled boots on Umar.
  R2 g1 setup: the popup said "reflective grey padded work top" was removed,
    the inventory kept it (a required TORSO card), and gm_brief's "only these"
    list left it out. R1 g2: the same for "chinos".
  R1 g1 / R1 g2 / R2 g2: amnesia arrivals stripped the items the backstory
    gives the character ("her only possession a cracked compass", "a
    tattered satchel of medical tools", "her old tools"); R2 g1 was a
    "hidden" mode whose story remembers everything and was stripped as amnesia.
  R2 g1: the backstory awoke "in the ruins of the sky-temple of Vael'Kara"
    while play started at The Far Platform.
  R2 g1 turn 4: "I pocket the crystal" granted a new "glowing shard" beside
    the held data crystal.
  R2 g2: an ordinary road laborer started Frostbite Whisper at rank B; the
    setup had given it F.
  R2 g1 / R2 g2 / R1: split fact titles were the first five words
    ("Survivors harness forbidden magic and") or one word ("Power").
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-live-starter-35-"))
_ENV = {
    **isolated_data_env(str(_TMP)),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)
# The player's launcher env: the narration pipeline in DSL mode. Scoped to the
# tests that build the writer's packet, so it does not leak into other modules.
LAUNCHER_ENV = {
    "AI_RPG_NARRATION_PIPELINE": "1",
    "AI_RPG_CONSOLIDATE": "1",
    "AI_RPG_FAST_VERIFICATION": "1",
    "AI_RPG_DSL_SKIP_VERIFY": "1",
    "AI_RPG_DRAFT_MODE": "dsl",
}

from app import db, world  # noqa: E402
from app import proficiencies as prof  # noqa: E402
from app import world_facts as wf  # noqa: E402
from app.narration_pipeline import (  # noqa: E402
    NarrationLedger,
    build_paragraph_briefs,
    entity_roster,
    plan_paragraph_budget,
)
from app.setup_coherence import align_backstory_arrival, arrival_place  # noqa: E402
from app.starter_logic import (  # noqa: E402
    classify_arrival,
    classify_item,
    evaluate_item,
    fact_check_starter_loadout,
    reconcile_with_seeded,
)

# --- live strings -----------------------------------------------------------

G1_STORY = (
    "Noor Ibrahim was a desert cartographer in the scorching dunes of Almaris, mapping forgotten trade routes "
    "when a sandstorm swallowed her expedition whole. She awoke in the ruins of the sky-temple of Vael'Kara, her "
    "fingertips glowing with the faint pulse of ancient celestial runes. Now, she seeks to unravel the temple's "
    "secrets to find her lost team, while her growing connection to the temple's dormant magic threatens to "
    "consume her."
)
G2_STORY = (
    "Erin Zielinski was a road laborer in the frostbitten city of Varnhold, where she earned a meager living "
    "hauling supplies for caravans that barely made it past the blizzards. One storm night, a mysterious ritual "
    "at the edge of the city left her frozen solid, only to thaw and wake in the snowdrifts near The Frostbound "
    "Crossroads, her memories wiped clean. She now clings to the remnants of her old tools, hoping to find work "
    "with the scattered settlers who brave the frontier."
)
R1G1_STORY = (
    "Constance Skinner was a street cart vendor in the port city of Veymar, where she bartered with smugglers "
    "and survived on the razor-thin margin between debt and survival. A cargo ship's sudden explosion and the "
    "subsequent collapse of the dock's rusted gantry left her stranded on the edge of the Whispering Wastes, her "
    "only possession a cracked compass that pointed not north, but toward the next desperate choice."
)
R1G2_STORY = (
    "Kavya Ward was a caravan medic in the trade city of Virelle, tending to wounds and ailments in exchange for "
    "coin and supplies. During a sandstorm, the caravan's transport truck overturned, and she was swept into a "
    "hidden cave by the wind, emerging days later at The Wasteland's Edge with no memory of how she got there, "
    "only a tattered satchel of medical tools and a determination to survive."
)

# R2 g2 turn 1 packet: the beat never names the gloves.
G2_CONTEXT = {
    "current_location": {"code": "L1", "name": "The Frostbound Crossroads"},
    "locations": [{"code": "L1", "name": "The Frostbound Crossroads"}],
    "npcs": [
        {"code": "A", "name": "Whitney Garcia", "role": "nurse", "location": "L1"},
        {"code": "B", "name": "Logan Price", "role": "trapper", "location": "L1"},
    ],
    "inventory": [
        {"code": "I1", "name": "frostbitten leather boots", "equipped_slot": "FEET"},
        {"code": "I2", "name": "patched white tunic", "equipped_slot": "TORSO"},
        {"code": "I4", "name": "work gloves", "equipped_slot": "WRIST"},
        {"code": "I5", "name": "tin of salve", "equipped_slot": ""},
    ],
}
G2_DRAFT = {
    "narration": (
        "You find yourself at the Frostbound Crossroads, where the wind cuts through the snow. "
        "Whitney Garcia, the nurse, tends a portable heater near a makeshift shelter.\n\n"
        "Logan Price, the trapper, looks up from his snares."
    )
}
CONFIG = {"mle_model": "qwen3:8b", "context_window": 32768, "response_token_cap": 1000}


def _briefs(player_input, draft, context=G2_CONTEXT, ops=""):
    budget = plan_paragraph_budget(context, player_input, CONFIG)
    ledger = NarrationLedger(turn=1, player_input=player_input, budget=budget)
    return build_paragraph_briefs(budget, context, player_input, ledger, ops, draft=draft)


class GearStaysOnThePlayer(unittest.TestCase):
    """#35-gear-bleed-npc"""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, LAUNCHER_ENV)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_unnamed_item_is_not_offered_to_the_beat(self):
        names = {row["name"] for row in entity_roster(G2_CONTEXT, G2_DRAFT)}
        self.assertNotIn("work gloves", names)
        self.assertNotIn("frostbitten leather boots", names)
        for brief in _briefs("I look around the crossroads.", G2_DRAFT):
            self.assertNotIn("work gloves", {row["name"] for row in brief["may_mention"]})

    def test_an_item_the_player_names_is_offered_as_theirs(self):
        rows = entity_roster(G2_CONTEXT, G2_DRAFT, player_input="I pull on my gloves and offer the salve.")
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["work gloves"]["kind"], "worn by the player (you)")
        self.assertEqual(by_name["tin of salve"]["kind"], "carried by the player (you)")

    def test_an_item_the_draft_or_ops_name_is_offered(self):
        draft = {"narration": "You tighten the laces of your boots against the cold."}
        self.assertIn("frostbitten leather boots", {r["name"] for r in entity_roster(G2_CONTEXT, draft)})
        rows = entity_roster(G2_CONTEXT, G2_DRAFT, ops_summary="USE I5")
        self.assertIn("tin of salve", {r["name"] for r in rows})

    def test_the_writer_is_told_the_items_are_the_players(self):
        from app import llm

        src = Path(llm.__file__).read_text(encoding="utf-8")
        self.assertIn("belong to the player", src)


class TheReportMatchesTheInventory(unittest.TestCase):
    """#35-popup-stripped-but-kept"""

    def test_work_top_and_chinos_are_clothes(self):
        for name in ("reflective grey padded work top", "chinos", "woven beanie"):
            self.assertEqual(classify_item(name)["bucket"], "body_worn", name)

    def test_a_slotted_card_counts_as_worn(self):
        arrival = classify_arrival(backstory_mode="amnesia", character_backstory="She remembers nothing.")
        row = evaluate_item("reflective grey padded tabard-thing", arrival, worn=True)
        self.assertEqual(row["decision"], "keep")

    def test_reconcile_drops_a_seeded_item_from_stripped(self):
        report = fact_check_starter_loadout(
            starter_equipment="mag-soled boots, sling pack, synth-weave trousers",
            backstory_mode="amnesia",
            memory_policy="no memory",
            character_backstory="She remembers nothing.",
            apply_fixes=True,
        )
        self.assertIn("sling pack", [s["name"] for s in report["stripped"]])
        fixed = reconcile_with_seeded(report, ["mag-soled boots", "sling pack", "synth-weave trousers"])
        self.assertNotIn("sling pack", [s["name"] for s in fixed["stripped"]])
        self.assertFalse(any("sling pack" in m for m in fixed["player_messages"]))
        only = re.search(r"Inventory at Start \(only these\): ([^.]*)", fixed["gm_brief"]).group(1)
        self.assertIn("sling pack", only)
        self.assertNotIn("Never reintroduce stripped items", fixed["gm_brief"])

    def test_start_stores_a_report_that_matches_the_inventory(self):
        os.environ.update(_ENV)
        db.init_db()
        world.start_playthrough(
            {
                "player_name": "Noor Ibrahim",
                "player_sex": "female",
                "start_location": "The Far Platform",
                "world_style": "apocalyptic mythic frontier",
                "backstory_mode": "amnesia",
                "memory_policy": "no memory",
                "character_backstory": "Noor woke with no memory on a metal platform.",
                "starter_equipment": "mag-soled boots, reflective grey padded work top, synth-weave trousers",
                "starter_gear": [
                    {"name": "mag-soled boots", "slot": "FEET", "required": True, "keep": True},
                    {"name": "reflective grey padded work top", "slot": "TORSO", "required": True, "keep": True},
                    {"name": "synth-weave trousers", "slot": "LEGS", "required": True, "keep": True},
                ],
            }
        )
        with db.connect() as conn:
            names = {str(r["name"]).lower() for r in conn.execute("SELECT name FROM inventory")}
            options = json.loads(
                conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()[0]
            )
        logic = options.get("starter_logic") or {}
        stripped = {str(s.get("name") or "").lower() for s in logic.get("stripped") or []}
        self.assertIn("reflective grey padded work top", names)
        self.assertFalse(stripped & names, (stripped, names))
        self.assertFalse(any("work top" in m for m in logic.get("player_messages") or []))
        only = re.search(r"Inventory at Start \(only these\): ([^.]*)", logic.get("gm_brief") or "")
        self.assertTrue(only and "reflective grey padded work top" in only.group(1), logic.get("gm_brief"))


class TheBackstoryKeepsWhatItGives(unittest.TestCase):
    """#35-amnesia-strips-backstory-items"""

    def test_her_only_possession_is_kept(self):
        a = classify_arrival(
            backstory_mode="nameless drifter", memory_policy="details emerge through choices", character_backstory=R1G1_STORY
        )
        self.assertEqual(a["arrival"], "amnesia_spawn")
        self.assertEqual(evaluate_item("cracked compass", a, character_backstory=R1G1_STORY)["decision"], "keep")
        self.assertEqual(evaluate_item("doctor's bag", a, character_backstory=R1G1_STORY)["decision"], "strip")

    def test_the_medic_keeps_her_satchel_of_tools_once(self):
        report = fact_check_starter_loadout(
            starter_equipment="sandals, chinos, satchel of medical tools, weathered canvas satchel",
            backstory_mode="nameless drifter",
            memory_policy="details emerge through choices",
            character_backstory=R1G2_STORY,
            apply_fixes=True,
        )
        kept = [k["name"] for k in report["kept"]]
        self.assertIn("satchel of medical tools", kept)
        self.assertIn("chinos", kept)
        self.assertNotIn("weathered canvas satchel", kept)

    def test_the_laborer_keeps_one_of_her_old_tools(self):
        report = fact_check_starter_loadout(
            starter_equipment="frostbitten leather boots, woven beanie, iron pickaxe, worn satchel",
            backstory_mode="amnesia",
            memory_policy="details emerge through choices",
            character_backstory=G2_STORY,
            apply_fixes=True,
        )
        kept = [k["name"] for k in report["kept"]]
        self.assertIn("iron pickaxe", kept)
        self.assertIn("woven beanie", kept)
        self.assertNotIn("worn satchel", kept)

    def test_hidden_with_a_remembered_past_is_not_amnesia(self):
        a = classify_arrival(backstory_mode="hidden", memory_policy="former life fragments", character_backstory=G1_STORY)
        self.assertNotEqual(a["arrival"], "amnesia_spawn")
        lost = classify_arrival(backstory_mode="hidden", memory_policy="no memory of the past", character_backstory=G1_STORY)
        self.assertEqual(lost["arrival"], "amnesia_spawn")
        self.assertEqual(
            classify_arrival(backstory_mode="amnesia", character_backstory=G2_STORY)["arrival"], "amnesia_spawn"
        )


class TheBackstoryArrivesWherePlayStarts(unittest.TestCase):
    """#35-backstory-arrival-vs-start-location"""

    def test_a_descriptive_place_is_seen_and_replaced(self):
        self.assertEqual(arrival_place(G1_STORY), "the ruins of the sky-temple of Vael'Kara")
        story, changed = align_backstory_arrival(G1_STORY, "The Far Platform")
        self.assertTrue(changed)
        self.assertIn("She awoke in The Far Platform, her fingertips glowing", story)
        self.assertNotIn("ruins of the sky-temple", story)

    def test_the_other_live_stories_are_left_alone(self):
        for story, start in (
            (G2_STORY, "The Frostbound Crossroads"),
            (R1G1_STORY, "Edge of the Whispering Wastes"),
            (R1G2_STORY, "The Wasteland's Edge"),
        ):
            self.assertEqual(align_backstory_arrival(story, start), (story, False), start)

    def test_a_non_place_after_the_verb_is_not_a_place(self):
        story = "Mara woke in a cold sweat, the dream still clinging to her."
        self.assertEqual(align_backstory_arrival(story, "The Far Platform"), (story, False))

    def test_a_region_sharing_a_word_is_kept(self):
        story = "Ash arrived in Eldoria, tired and hungry."
        self.assertEqual(align_backstory_arrival(story, "Eldoria's Edge"), (story, False))


class PocketingAHeldItemGrantsNothing(unittest.TestCase):
    """#35-pocket-duplicate-grant"""

    NARRATION = "You pocket the glowing shard and follow the Guild watcher through the maze of warehouses."
    STATE = {"inventory": [{"name": "mag-soled boots"}, {"name": "data crystal"}]}

    def test_the_players_words_name_the_held_crystal(self):
        turn: dict = {}
        got = world.ground_acquisitions(
            turn, self.NARRATION, self.STATE, player_input="I pocket the crystal and follow the Guild watcher"
        )
        self.assertEqual(got, [])
        self.assertFalse(turn.get("inventory_changes"))

    def test_a_held_item_by_head_noun_is_not_new(self):
        got = world.ground_acquisitions({}, "You pocket the cracked crystal and turn away.", self.STATE)
        self.assertEqual(got, [])

    def test_a_new_object_is_still_granted(self):
        got = world.ground_acquisitions(
            {}, "You pick up the rusted key and step back.", self.STATE, player_input="I grab the key off the table"
        )
        self.assertEqual(got, ["rusted key"])

    def test_play_turn_passes_the_input(self):
        src = Path(world.__file__).read_text(encoding="utf-8")
        call = re.search(r"acquisitions = ground_acquisitions\((.{0,200}?)\n\s*\)", src, re.S)
        self.assertTrue(call and "player_input=" in call.group(1), call and call.group(1))


LABELS = ["F", "E", "D", "C", "B", "A", "S", "SS", "SSS"]
G2_OPTIONS = {
    "rank_scale": "F,E,D,C,B,A,S,SS,SSS",
    "session_theme": {"power_fantasy": {"start_power": "ordinary", "growth": "steady"}},
    "custom_skills": "Frostbite Whisper (F), Snowbound Echo (C), Frostweave (C), crafting through communal effort (B), "
    "survival through shared knowledge (B)",
    "custom_skills_setup": "Frostbite Whisper (F), Snowbound Echo (C), Frostweave (C), crafting through communal effort (B), "
    "survival through shared knowledge (B)",
    "player_name": "Erin Zielinski",
    "character_backstory": G2_STORY,
}
G2_SETTLE = "\n".join(
    [
        "SKILL|Frostbite Whisper|B|crafting through communal effort|survival through shared knowledge",
        "SKILL|Snowbound Echo|C|crafting through communal effort|survival through shared knowledge",
        "SKILL|Frostweave|C|crafting through communal effort|survival through shared knowledge",
    ]
)


class AnOrdinaryStartIsLow(unittest.TestCase):
    """#35-rank-B-ordinary-laborer"""

    def test_ordinary_cap_is_low(self):
        cap = prof.start_rank_cap(G2_OPTIONS, LABELS)
        self.assertLessEqual(cap, 2)
        self.assertGreaterEqual(cap, 1)
        strong = {"session_theme": {"power_fantasy": {"start_power": "strong"}}}
        self.assertEqual(prof.start_rank_cap(strong, LABELS), 8)

    def test_settlement_keeps_the_rank_setup_gave(self):
        os.environ.update(_ENV)
        db.init_db()
        with db.connect() as conn:
            prof.apply_settlement(conn, G2_SETTLE, dict(G2_OPTIONS))
            rows = {r["name"]: r["start_rank"] for r in prof.proficiency_rows(conn)}
        self.assertEqual(rows.get("Frostbite Whisper"), "F")
        self.assertLessEqual(LABELS.index(rows.get("Snowbound Echo", "SSS")), 2)

    def test_prompt_sends_the_ceiling_as_context(self):
        user = json.loads(prof.settle_prompt(dict(G2_OPTIONS), []))
        self.assertEqual(user["highest_start_rank"], "D")


G1_STYLE = (
    "In the Apocalyptic Mythic Frontier, survivors harness forbidden magic and spacefaring salvage to rebuild. Power "
    "is earned through calculated risks and skill mastery, with each advancement demanding a permanent sacrifice. The "
    "world's scarce resources and grounded adventure tone ensure every gain is hard-earned, aligning with fair player "
    "agency and mythic progression."
)
G2_STYLE = (
    "Modern urban elements blend with ancient frontier ruins, creating hidden zones where magic flickers beneath the "
    "surface of lawless settlements."
)
R1G1_STYLE = (
    "Setting frame: Fantasy RPG. Power here is earned: talent starts small and grows with risk and training; nobody "
    "is born strong. DM stance: always keep fair DM player-agency stance"
)
R1G2_STYLE = (
    "The land is a brutal frontier where survival hinges on crafting over combat, and settlements are isolated "
    "enclaves bound by thin law. Magic, when it exists, is a dangerous secret wielded by outcasts, while the harsh "
    "climate and scarcity of resources force communities to rely on mutual aid and cunning to endure."
)
_JOINERS = {"and", "or", "but", "with", "of", "in", "on", "to", "for", "by", "the", "a", "an", "when", "where", "here"}


class FactTitlesAreNounPhrases(unittest.TestCase):
    """#35-fact-titles-first-words"""

    def _titles(self, style):
        return [wf._title_for(s) for s in wf.split_sentences(style)]

    def test_no_title_ends_on_a_joiner_or_is_one_word(self):
        for style in (G1_STYLE, G2_STYLE, R1G1_STYLE, R1G2_STYLE):
            for title in self._titles(style):
                words = title.split()
                self.assertGreaterEqual(len(words), 2, title)
                self.assertNotIn(words[-1].lower(), _JOINERS, title)

    def test_the_live_titles(self):
        titles = self._titles(G1_STYLE)
        self.assertEqual(titles[0], "Survivors harness forbidden magic")
        self.assertEqual(titles[1], "Power earned through calculated risks")
        self.assertEqual(titles[2], "World's scarce resources")
        self.assertEqual(self._titles(G2_STYLE), ["Modern urban elements"])
        r1 = self._titles(R1G1_STYLE)
        self.assertIn("Nobody is born strong", r1)
        self.assertIn("DM stance", r1)
        self.assertNotIn("Born nobody", r1)
        r2 = self._titles(R1G2_STYLE)
        self.assertNotIn("Magic when it exists", r2)
        self.assertNotIn("Land", r2)

    def test_the_post_start_pass_retitles_split_rows(self):
        os.environ.update(_ENV)
        db.init_db()
        with db.connect() as conn:
            wf.ensure_seeded(conn)
            wf.store_fact(conn, {"kind": "magic", "title": "Survivors harness forbidden magic and",
                                 "text": "In the Apocalyptic Mythic Frontier, survivors harness forbidden magic and spacefaring salvage to rebuild.",
                                 "source": "split"})
            report = wf.apply_refinement(conn, "")
            titles = [r["title"] for r in conn.execute("SELECT title FROM world_facts WHERE source = 'split'")]
        self.assertIn("Survivors harness forbidden magic", titles)
        self.assertTrue(report.get("retitled"))


if __name__ == "__main__":
    unittest.main()
