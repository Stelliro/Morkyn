"""
Playtest #22: game 2 (auto-ab564b3c-t00004) still rolled slogan proficiencies.

The setup roll gave "master the dance of shadows (E), learn from the ancients
(C), forge unbreakable bonds (D)"; the post-start pass stored Dance of Shadows
C, Ancient Lore C and Unbreakable Bonds D (adjusted: []) for an idea that
says "start ordinary with one weak compounding seed power"; and rule F7 was
titled "Crafting Mastery" over the text "Unbreakable Bonds requires a special
material".

These tests check, with the save's own strings:
  - the custom_skills ask carries 3-5 proficiency name shapes drawn per call
    from a world-filtered pool, different from roll to roll;
  - a verb-led name is found structurally and becomes its noun form when its
    object is the skill, else is re-asked once, else dropped (setup roll and
    post-start pass alike);
  - the rank cap follows the idea's own words, not only a stale session
    theme; the seed may stand one step up only when the idea names it;
  - Start floors the stored power fantasy with the idea;
  - a rule's title comes from its own text.
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-proficiency-names-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
        "AI_RPG_POST_START_MODEL": "off",
    }
)

from app import db, llm, world  # noqa: E402
from app import example_pools as ep  # noqa: E402
from app import proficiencies as prof  # noqa: E402
from app import world_facts as wf  # noqa: E402
from app.db import connect  # noqa: E402
from app.setup_composer import floor_power_fantasy  # noqa: E402

# Strings from the game-2 save (start.json, world.json).
IDEA = (
    "Overpowered progression in any setting: start ordinary with one weak compounding seed power that "
    "snowballs toward late-game OP (rank F up through S/SS/SSS). Growth Math makes the climb calculable; "
    "passives allowed; more powers can unlock later. Normal difficulty; mythic progression tone; local "
    "stakes early; fair DM."
)
ROLLED = "master the dance of shadows (E), learn from the ancients (C), forge unbreakable bonds (D)"
STORED_THEME = {
    "adapter_hint": "isekai_rpg",
    "genre": "endless fantasy",
    "isekai": True,
    "power_fantasy": {
        "start_power": "ordinary",
        "growth": "steady",
        "system_ui": False,
        "skill_summary": "gain magical aptitude and combat prowess through trials",
    },
}
GAME2 = {
    "world_style": "frontier dark fantasy",
    "custom_style": (
        "In a land of mist-shrouded forests and storm-wracked coasts, the kingdom of Eldoria is ruled by a "
        "council of mages and warrior-princes."
    ),
    "tech_level": "medieval",
    "magic_level": "rare",
    "rank_scale": "F,E,D,C,B,A,S,SS,SSS",
    "skill_style": "standard",
    "proficiency_access": "familiar actions free",
    "character_backstory": (
        "Miriam Shaw, a stagehand with a knack for rigging and a passion for storytelling, was transported "
        "to the new world after a mysterious ferry accident. In her former life, she worked as a carpenter's "
        "apprentice in a small village, crafting intricate traps and mechanisms."
    ),
    "special_abilities": [
        {"name": "Luminous Veil", "description": "Create a shimmering barrier of light.", "locked": True},
        {"name": "Whispering Fates", "description": "Whisper words of fate into the wind."},
    ],
    "session_theme": STORED_THEME,
    "custom_skills": ROLLED,
}
# The post-start pass's lines, as stored in player_proficiencies and F7.
SETTLE_LINES = "\n".join([
    "SKILL|Dance of Shadows|C|Practice dark arts and shadow manipulation in secret|Cannot master the dance of shadows without a dark ritual",
    "SKILL|Ancient Lore|C|Study and learn from ancient texts and artifacts|Cannot unlock forbidden knowledge without a rare artifact",
    "SKILL|Unbreakable Bonds|D|Forge unbreakable connections between people and objects|Cannot create bonds stronger than the target's will",
    "RULE|Crafting Mastery|Unbreakable Bonds requires a special material",
])
LABELS = prof.rank_labels(GAME2)


def setUpModule():
    os.environ.update(isolated_data_env(str(_TMP)))
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _fresh(options: dict, idea: str | None = IDEA) -> dict:
    with connect() as conn:
        wf.ensure_world_fact_tables(conn)
        wf.clear_world_facts(conn)
        prof.clear_proficiencies(conn)
        conn.execute("DELETE FROM player_skills")
        conn.execute("DELETE FROM settings WHERE key = 'game_start_form'")
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('playthrough_options', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(options),),
        )
        if idea is not None:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('game_start_form', ?)",
                (json.dumps({"controls": [], "randomize_idea": idea}),),
            )
    return options


class TheAskShowsDrawnNameShapes(unittest.TestCase):
    def test_three_to_five_fresh_shapes_per_roll(self):
        draws = [tuple(ep.setup_examples("custom_skills", GAME2, rng=random.Random(seed))) for seed in range(12)]
        for draw in draws:
            self.assertTrue(3 <= len(draw) <= 5, draw)
            for name in draw:
                self.assertEqual(prof.name_shape_errors(name), [], name)
        self.assertGreater(len(set(draws)), 6)

    def test_shapes_follow_the_world(self):
        rng = random.Random(9)
        no_magic = {"world_style": "cyberpunk megacity", "tech_level": "near future", "magic_level": "none"}
        inland = {"world_style": "high plateau steppe", "tech_level": "medieval", "magic_level": "rare"}
        sect = {"world_style": "xianxia cultivation sect politics", "tech_level": "medieval", "magic_level": "cultivation"}
        blob = lambda setup: " ".join(" ".join(ep.setup_examples("custom_skills", setup, n=5, rng=rng)) for _ in range(80))
        cyber = blob(no_magic)
        for word in ("Rune", "Ward", "Hedge Magic", "Qi ", "Thatching", "Falconry"):
            self.assertNotIn(word, cyber)
        self.assertNotIn("Net Mending", blob(inland))
        self.assertIn("Qi Circulation", blob(sect) + " ".join(ep.setup_examples("custom_skills", sect, n=40, rng=rng)))

    def test_a_backstory_trade_is_offered(self):
        hits = sum(
            any(name in ("Carpentry", "Rigging", "Trap Making", "Storytelling", "Joinery") for name in
                ep.setup_examples("custom_skills", GAME2, rng=random.Random(seed)))
            for seed in range(20)
        )
        self.assertEqual(hits, 20)

    def test_used_names_are_not_drawn(self):
        ctx = ep.setup_context(GAME2)
        for seed in range(30):
            self.assertNotIn("Carpentry", ep.draw("proficiency_name", ctx, 5, random.Random(seed), ["carpentry"]))

    def test_the_roll_prompt_carries_the_draw_and_differs(self):
        prompts = []
        for _ in range(3):
            captured: dict = {}

            def fake_chat(system, user, **kwargs):
                captured.setdefault("user", user)
                raise RuntimeError("stop after prompt build")

            original = llm._chat_json
            llm._chat_json = fake_chat
            try:
                llm.generate_setup_randomization("field:custom_skills", dict(GAME2, custom_skills=""))
            except Exception:
                pass
            finally:
                llm._chat_json = original
            prompts.append(json.loads(captured["user"]))
        lines = [next((r for r in p["rules"] if r.startswith(ep.examples_rule("custom_skills"))), "") for p in prompts]
        self.assertTrue(all(lines), lines)
        self.assertGreater(len(set(lines)), 1, lines)
        self.assertNotIn("Dance of Shadows", json.dumps(prompts[0]))


    def test_the_group_roll_carries_shapes_too(self):
        # The powers phase rolls custom_skills in a group; its contract shows
        # the drawn name form as well, fresh per call.
        from app.llm import _field_contracts_for_prompt

        setup = {"world_style": "frontier dark fantasy", "tech_level": "medieval", "magic_level": "rare"}
        seen = set()
        for _ in range(4):
            slim = _field_contracts_for_prompt(["custom_skills", "special_abilities"], setup)["custom_skills"]
            self.assertIn("never a verb phrase", slim["examples_rule"])
            self.assertTrue(3 <= len(slim["examples"]) <= 5)
            seen.add(tuple(slim["examples"]))
        self.assertGreater(len(seen), 1)


class VerbLedNamesAreFoundStructurally(unittest.TestCase):
    def test_the_save_slogans_lead_with_verbs(self):
        for name in ("master the dance of shadows", "learn from the ancients", "forge unbreakable bonds",
                     "weave light", "braid destiny", "to master swordplay", "Harmonize Spirits"):
            self.assertTrue(prof.leading_verb(name), name)
            self.assertIn("name starts with a verb", prof.name_shape_errors(name), name)

    def test_nouns_that_look_like_verbs_stay_names(self):
        for name in ("Dance of Shadows", "Trade Lore", "Track Reading", "Master of Blades", "Barge Poling",
                     "Rope Splicing", "Lore of Tides", "Herb Lore"):
            self.assertEqual(prof.leading_verb(name), "", name)

    def test_verb_spelled_nouns_lead_names(self):
        for name in ("Hide Tanning", "Open Water Swimming", "Close Combat"):
            self.assertEqual(prof.leading_verb(name), "", name)
        self.assertEqual(prof.leading_verb("hide in the shadows"), "hide")

    def test_a_strong_compounding_start_is_not_floored(self):
        labels = prof.rank_labels({"rank_scale": "F,E,D,C,B,A,S"})
        strong = {"session_theme": {"power_fantasy": {"start_power": "strong", "growth": "compounding"}}}
        self.assertEqual(prof.start_rank_cap(strong, labels), 6)
        ordinary = {"session_theme": {"power_fantasy": {"start_power": "ordinary", "growth": "compounding"}}}
        self.assertEqual(prof.start_rank_cap(ordinary, labels), 0)

    def test_noun_form_only_when_the_object_is_the_skill(self):
        self.assertEqual(prof.noun_form("master the dance of shadows"), "Dance of Shadows")
        self.assertEqual(prof.noun_form("hone your herb lore"), "Herb Lore")
        self.assertEqual(prof.noun_form("to master swordplay"), "Swordplay")
        for name in ("learn from the ancients", "forge unbreakable bonds", "braid destiny", "study the stars"):
            self.assertEqual(prof.noun_form(name), "", name)


class TheSetupRollIsSettled(unittest.TestCase):
    def test_game_two_string(self):
        asked: list[dict] = []

        def ask(system, user):
            asked.append(json.loads(user))
            return "1|Ancient Lore\n2|NONE"

        text, report = prof.settle_setup_text(ROLLED, GAME2, power_fantasy=STORED_THEME["power_fantasy"], idea=IDEA, ask=ask)
        self.assertEqual(text, "Dance of Shadows (F), Ancient Lore (F)")
        self.assertEqual(report["dropped"], ["forge unbreakable bonds"])
        self.assertEqual(len(asked), 1)
        self.assertEqual([p["phrase"] for p in asked[0]["phrases"]], ["learn from the ancients", "forge unbreakable bonds"])
        self.assertTrue(3 <= len(asked[0]["name_shapes"]) <= 5)
        self.assertNotIn("Dance of Shadows", asked[0]["name_shapes"])

    def test_a_failed_reask_drops_and_rules_pass(self):
        def ask(system, user):
            raise RuntimeError("model down")

        text, report = prof.settle_setup_text(
            ROLLED + ", new proficiencies need a teacher met in play", GAME2, idea=IDEA, ask=ask
        )
        self.assertEqual(text, "Dance of Shadows (F), new proficiencies need a teacher met in play")
        self.assertEqual(report["dropped"], ["learn from the ancients", "forge unbreakable bonds"])

    def test_the_seed_may_stand_one_step_up_when_the_idea_says(self):
        idea = "Start weak: one seed power at rank E that compounds."
        text, _ = prof.settle_setup_text(
            "weak seed skill: Luminous Veil (C; tracked by uses), Carpentry (D; tracked by jobs)", GAME2, idea=idea,
            ask=lambda s, u: "",
        )
        self.assertEqual(text, "weak seed skill: Luminous Veil (E; tracked by uses), Carpentry (F; tracked by jobs)")

    def test_the_roll_returns_the_settled_text(self):
        def fake_json(system, user, **kwargs):
            return {"custom_skills": ROLLED}

        def fake_content(system, user, **kwargs):
            return "1|Ancient Lore\n2|Rope Splicing"

        # No idea here: with one, the weak-seed quality gate wants a "weak seed skill:" lead and
        # the fake's retries fall back to the seed pool text, which is not what this checks.
        current = dict(GAME2, custom_skills="")
        originals = llm._chat_json, llm._chat_content
        llm._chat_json, llm._chat_content = fake_json, fake_content
        try:
            out = llm.generate_setup_randomization("field:custom_skills", current)
        finally:
            llm._chat_json, llm._chat_content = originals
        value = str(out.get("custom_skills") or out.get("values", {}).get("custom_skills") or "")
        self.assertNotIn("master the", value)
        self.assertNotIn("forge unbreakable", value)
        self.assertEqual(value, "Dance of Shadows (E), Ancient Lore (C), Rope Splicing (D)")


class TheRollKeepsItsParentheses(unittest.TestCase):
    # Found in the live rolls for this fix: the comma cleanup split inside the
    # parentheses and deduped "hard limit S)" out of every later phrase, and
    # the seed alignment ate "(F," after a seed name.
    def test_repeated_details_are_kept(self):
        rolled = (
            "Net Mending (D, tracked by number of nets repaired, hard limit S), "
            "Barge Poling (D, tracked by miles poled, hard limit S)"
        )
        self.assertEqual(llm._comma_separated_phrases(rolled), rolled)
        self.assertEqual(llm._comma_separated_phrases("Rope Splicing (E)\nRope Splicing (E)"), "Rope Splicing (E)")

    def test_seed_alignment_keeps_the_rank(self):
        rolled = "weak seed skill: Luminous Weaving (F, rank tracked by light barrier complexity; XP from defenses)"
        self.assertEqual(
            llm.align_seed_skill_with_abilities(rolled, [{"name": "Luminous Veil"}]),
            "weak seed skill: Luminous Veil (F, rank tracked by light barrier complexity; XP from defenses)",
        )
        self.assertEqual(
            llm.align_seed_skill_with_abilities("weak seed skill: Ember Forging, F (rank)", [{"name": "Ember Root"}]),
            "weak seed skill: Ember Root, F (rank)",
        )


    def test_a_repeated_bare_rank_is_kept(self):
        rolled = "Qi Circulation, F, tracked by daily meditations, Scar Library, F, tracked by touch"
        self.assertEqual(llm._comma_separated_phrases(rolled), rolled)

    def test_only_the_opening_label_is_the_start_rank(self):
        # Live roll, ordinary start on E..S (cap C): "capped at S" is the limit.
        opts = dict(GAME2, rank_scale="E,D,C,B,A,S")
        rolled = (
            "Net Mending (D, tracked by repaired nets, capped at A), "
            "Current Sense (weak, seed, tracked by water awareness, capped at S), "
            "Barge Poling (A, tracked by crossings, capped at S)"
        )
        text, report = prof.settle_setup_text(rolled, opts, power_fantasy={"start_power": "ordinary"}, ask=lambda s, u: "")
        self.assertEqual(
            text,
            "Net Mending (D, tracked by repaired nets, capped at A), "
            "Current Sense (weak, seed, tracked by water awareness, capped at S), "
            "Barge Poling (C, tracked by crossings, capped at S)",
        )
        self.assertEqual(report["ranks_lowered"], ["Barge Poling"])

    def test_a_bare_rank_after_its_name_is_capped(self):
        text, report = prof.settle_setup_text(
            "Qi Circulation, C, tracked by daily meditations", GAME2, idea=IDEA, ask=lambda s, u: ""
        )
        self.assertEqual(text, "Qi Circulation, F, tracked by daily meditations")
        self.assertEqual(report["ranks_lowered"], ["C"])


class ThePostStartPass(unittest.TestCase):
    def test_game_two_rows_start_at_the_bottom(self):
        opts = _fresh(dict(GAME2))
        with connect() as conn:
            report = prof.apply_settlement(conn, SETTLE_LINES, opts)
            rows = prof.proficiency_rows(conn)
            rules = prof.proficiency_rules(conn)
        self.assertEqual([(r["name"], r["start_rank"]) for r in rows],
                         [("Dance of Shadows", "F"), ("Ancient Lore", "F"), ("Unbreakable Bonds", "F")])
        self.assertIn("SKILL Dance of Shadows: start rank lowered to F", report["adjusted"])
        self.assertEqual(rules[0]["title"], "Unbreakable Bonds Limit")
        self.assertIn("RULE Crafting Mastery: titled Unbreakable Bonds Limit from its text", report["adjusted"])

    def test_the_stale_theme_alone_was_the_hole(self):
        # Without the idea, game 2's stored theme ("ordinary") allows B: why adjusted was [].
        self.assertEqual(prof.start_rank_cap(GAME2, LABELS), 4)
        self.assertEqual(prof.start_rank_cap(GAME2, LABELS, IDEA), 0)
        self.assertEqual(prof.seed_rank_cap(GAME2, LABELS, IDEA), 0)
        self.assertEqual(prof.seed_rank_cap(GAME2, LABELS, "weak start, seed at rank D"), 1)

    def test_verb_led_skill_lines(self):
        opts = _fresh(dict(GAME2))
        lines = "\n".join([
            "SKILL|master the dance of shadows|F|nights practised|no daylight use",
            "SKILL|forge unbreakable bonds|F|oaths kept|no bond over a will",
            "SKILL|learn from the ancients|F|texts read|no forbidden lore",
        ])
        with connect() as conn:
            report = prof.apply_settlement(conn, lines, opts, rename=lambda items: {0: "Oath Keeping"})
            names = [r["name"] for r in prof.proficiency_rows(conn)]
        self.assertEqual(names, ["Dance of Shadows", "Oath Keeping"])
        self.assertIn("SKILL master the dance of shadows: a verb phrase, named Dance of Shadows", report["adjusted"])
        self.assertIn("SKILL learn from the ancients: a verb phrase that names no skill", report["rejected"])

    def test_a_model_title_from_the_text_is_kept(self):
        opts = _fresh(dict(GAME2))
        with connect() as conn:
            prof.apply_settlement(conn, "RULE|Mentor Training|New proficiencies need a mentor's first lesson.", opts)
            self.assertEqual(prof.proficiency_rules(conn)[0]["title"], "Mentor Training")

    def test_settle_prompt_shows_shapes_and_the_floored_start(self):
        user = json.loads(prof.settle_prompt(GAME2, ["Luminous Veil"], IDEA))
        self.assertEqual(user["highest_start_rank"], "F")
        self.assertEqual(user["character"]["start_power"], "near_useless")
        self.assertTrue(3 <= len(user["name_shapes"]) <= 5)


class StartFloorsThePowerFantasy(unittest.TestCase):
    def test_floor(self):
        self.assertEqual(
            floor_power_fantasy(STORED_THEME["power_fantasy"], IDEA)["start_power"], "near_useless"
        )
        strong = {"start_power": "strong", "growth": "steady"}
        self.assertEqual(floor_power_fantasy(strong, "a calm farming life"), strong)

    def test_start_stores_the_floored_theme(self):
        world.start_playthrough(
            dict(
                GAME2,
                custom_skills="",
                player_name="Harrow Ames",
                special_ability_origin="none",
                setup_form={"controls": [], "randomize_idea": IDEA},
            )
        )
        pf = world.get_state()["settings"]["playthrough_options"]["session_theme"]["power_fantasy"]
        self.assertEqual((pf["start_power"], pf["growth"]), ("near_useless", "compounding"))


if __name__ == "__main__":
    unittest.main()
