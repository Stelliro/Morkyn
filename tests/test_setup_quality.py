"""Regression tests for setup / backstory composition quality.

Every case here is a defect that shipped: the composer replacing the person the
player wrote, a native character silently converted to an isekai one, a gate that
rejected its own generator's phrasing, `hash()`-seeded rewrites that were both
identical and unreproducible, pocket contents belonging to somebody else's job,
and run-on sentences from stripped terminators.

Run:  python -m unittest tests.test_setup_quality
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-setupq-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

import app.setup_composer as sc  # noqa: E402
import app.starter_logic as sl  # noqa: E402
from app.db import db_path  # noqa: E402


def _assert_isolated() -> None:
    if not str(db_path()).startswith(str(_TMP)):
        raise AssertionError(f"test isolation failed: AI_RPG_DB resolves to {db_path()!r}")


def setUpModule() -> None:
    """Re-pin paths: unittest imports every test module before running any test."""
    os.environ.update(_ENV)
    _assert_isolated()


_assert_isolated()

TECHNICIAN = (
    "A maintenance technician in a near-future city, specializing in repairing automated systems. "
    "They lived a routine life balancing work and family."
)
NOBLE_PLOT = (
    "They were a disgraced noble heir in a collapsing empire, forced into exile after a failed coup. "
    "Now they pose as a wandering merchant at a festival. Their weak seed skill Guest Right compounds."
)


class TestFormerLifeIsKept(unittest.TestCase):
    """The path is called stitch_arrival_keep_former_life; it must keep the former life."""

    def test_player_vocation_survives_the_rewrite(self):
        phrase = sc.former_life_phrase(TECHNICIAN)
        self.assertIn("maintenance technician", phrase)
        self.assertFalse(phrase.endswith("."))

    def test_native_fantasy_plot_is_not_treated_as_a_former_life(self):
        """A disgraced noble is a local plot, not a former *world* life — rewrite it."""
        self.assertEqual(sc.former_life_phrase(NOBLE_PLOT), "")

    def test_stitch_keeps_the_person_the_player_wrote(self):
        report = sl.fact_check_starter_loadout(
            starter_equipment="frayed maintenance vest, small tool pouch, water flask, worn boots",
            appearance="torso: frayed maintenance vest; feet: worn boots",
            backstory_mode="transmigrated",
            character_backstory=TECHNICIAN,
            intent={"isekai": True, "genre": "isekai fantasy"},
            world_style="Mundane isekai compound",
            tech_level="medieval",
            magic_level="cultivation",
            apply_fixes=True,
        )
        story = (report.get("character_backstory") or "").lower()
        self.assertEqual((report.get("vibe") or {}).get("path"), "stitch_arrival_keep_former_life")
        self.assertIn("technician", story)
        self.assertTrue(sc.transmigration_story_score(story)["ok"], story)

    def test_cliched_plot_is_still_fully_replaced(self):
        fixed = sc.ensure_isekai_arrival_beat(
            NOBLE_PLOT, mode="transmigrated", idea="isekai", world_style="Mundane isekai compound"
        ).lower()
        self.assertNotIn("guest right", fixed)
        self.assertNotIn("disgraced noble", fixed)
        self.assertTrue(sc.transmigration_story_score(fixed)["ok"], fixed)


class TestOriginRegisterIsScored(unittest.TestCase):
    """One ambiguous word must not outvote explicit local context."""

    def test_local_context_beats_a_single_ambiguous_word(self):
        """"gate office" in a fantasy compound is not an Earth office job."""
        got = sl.detect_origin_register(
            character_backstory="A compound clerk who tallies grain fees at the gate office.",
            backstory_mode="known",
        )
        self.assertEqual(got, sl.ORIGIN_LOCAL_WORLD)

    def test_decisive_markers_still_win_alone(self):
        for story, expected in (
            ("A salaryman who rode the subway every morning to a desk job.", sl.ORIGIN_MODERN_EARTH),
            ("A technician in a near-future city.", sl.ORIGIN_NEAR_FUTURE),
        ):
            with self.subTest(story=story):
                self.assertEqual(
                    sl.detect_origin_register(character_backstory=story, backstory_mode="transmigrated"),
                    expected,
                )

    def test_known_local_character_is_not_converted_to_transmigrated(self):
        report = sl.fact_check_starter_loadout(
            starter_equipment="mage robe, coin purse, plain boots",
            appearance="torso: mage robe; feet: plain boots",
            backstory_mode="known",
            character_backstory="A compound clerk who tallies grain fees at the gate office.",
            intent={},
            world_style="fantasy compound",
            tech_level="iron age",
            magic_level="rare",
        )
        self.assertEqual(report.get("backstory_mode"), "known")
        self.assertNotIn("not Earth", report.get("character_backstory") or "")
        # the actual point of that scenario still holds
        self.assertNotIn("mage robe", " ".join(k["name"].lower() for k in report["kept"]))


class TestArrivalDetection(unittest.TestCase):
    def test_the_gate_accepts_its_own_generators_phrasing(self):
        """"a lantern-lit market lane" comes from _TX_ARRIVALS and scored missing_arrival_place."""
        story = (
            "Before the transfer they were a middle-school math teacher who graded papers past midnight. "
            "Then came a wet stairwell fall that ended mid-breath; when awareness returned they were at a "
            "lantern-lit market lane that smelled of oil and wet rope, carrying a red pen and a bus pass "
            "that means nothing."
        )
        self.assertTrue(sc.transmigration_story_score(story)["has_arrival_place"], story)

    def test_a_former_life_place_is_not_an_arrival(self):
        for text in (
            "they worked in a city office for nine years and hated the commute",
            "they ran a market stall selling jars every weekend",
        ):
            with self.subTest(text=text):
                self.assertFalse(sc._has_structural_arrival(text))


class TestBackstorySeeding(unittest.TestCase):
    def test_repairs_are_varied(self):
        """The seed was abs(hash(text)), so every repair of a story was identical."""
        outs = {
            sc.ensure_isekai_arrival_beat(
                NOBLE_PLOT, mode="transmigrated", idea=f"isekai start {i}", world_style="Mundane isekai compound"
            )
            for i in range(10)
        }
        self.assertGreaterEqual(len(outs), 8, outs)

    def test_seed_is_stable_across_processes(self):
        code = (
            "import os,tempfile;"
            "t=tempfile.mkdtemp();os.environ['AI_RPG_DB']=t+'/w.db';"
            "os.environ['AI_RPG_SOURCE_INDEX']=t+'/si';"
            "import app.setup_composer as sc;"
            "print(sc._backstory_seed('story','idea','world','score'))"
        )
        outs = set()
        for hash_seed in ("0", "1", "12345"):
            env = {**os.environ, "PYTHONHASHSEED": hash_seed}
            outs.add(
                subprocess.run(
                    [sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(ROOT)
                ).stdout.strip()
            )
        self.assertEqual(len(outs), 1, f"seed drifted across processes: {outs}")

    def test_no_randomized_hash_seeds_remain(self):
        """Parsed, not grepped, so prose about the old bug does not trip it."""
        import ast

        offenders: list[str] = []
        for path in sorted((ROOT / "app").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "hash"
                ):
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(offenders, [], f"randomized hash() seeds remain: {offenders}")


class TestPocketsBelongToTheJob(unittest.TestCase):
    def test_every_job_has_a_tailored_pocket(self):
        for job in sc._TX_JOBS:
            with self.subTest(job=job):
                self.assertNotEqual(sc._pockets_for_job(job), sc._TX_POCKETS_NEUTRAL, job)

    def test_a_teachers_kit_does_not_go_to_a_librarian(self):
        self.assertNotIn(
            "a red pen, lesson notes in a tote, and a bus pass that means nothing",
            sc._pockets_for_job("public-library assistant reshelving late returns and quiet crises"),
        )

    def test_neutral_pockets_stay_available_so_variety_survives(self):
        for job in ("middle-school math teacher who graded papers past midnight", "line cook in a cramped kitchen"):
            with self.subTest(job=job):
                self.assertGreaterEqual(len(sc._pockets_for_job(job)), 3)


class TestGeneratedProse(unittest.TestCase):
    def test_article_agreement(self):
        for phrase, article in (
            ("apartment-building super", "an"),
            ("airport baggage handler", "an"),
            ("architecture intern", "an"),
            ("middle-school math teacher", "a"),
            ("university lecturer", "a"),
            ("one-room clerk", "a"),
            ("honest broker", "an"),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(sc._article_for(phrase), article, phrase)

    def test_generated_backstories_never_say_a_apartment(self):
        for seed in range(40):
            story = sc.build_transmigration_backstory(
                idea=f"ordinary life {seed}", world_style="frontier kingdom", seed=seed
            )
            with self.subTest(seed=seed):
                self.assertNotRegex(story.lower(), r"\ba [aeiou]", story)

    def test_localized_backstories_have_no_run_on_sentences(self):
        for old, vocation, seed_text in (
            ("A person of no fixed trade.", "ordinary compound laborer", "They kept to the yard gates."),
            ("A drifter.", "yard hand", "They swept the stalls"),
        ):
            out = sl._localize_backstory(
                old_story=old,
                vocation=vocation,
                seed=seed_text,
                world_style="frontier kingdom",
                keep_faint_otherworld_memory=True,
            )
            with self.subTest(vocation=vocation):
                self.assertIsNone(re.search(r"[a-z]\s+(Known|Strange|Work|Hook)\b", out), out)

    def test_sentence_join_keeps_existing_terminators(self):
        self.assertEqual(sl._sentence_join("They ran!", "Then rested."), "They ran! Then rested.")
        self.assertEqual(sl._sentence_join("They ran", "Then rested."), "They ran. Then rested.")
        self.assertEqual(sl._sentence_join("", "Then rested."), "Then rested.")
        self.assertEqual(sl._sentence_join("They ran.", ""), "They ran.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
