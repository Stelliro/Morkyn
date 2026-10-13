"""8B people and setup issues: #87 skill notes, #83 on/off duty, #73 (7B T38) one figure seeded twice."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-8b-people-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
        "AI_RPG_POST_START_MODEL": "off",
    }
)

from app import db, prompts, shifts, world  # noqa: E402
from app import proficiencies as prof  # noqa: E402
from app import world_facts as wf  # noqa: E402
from app.db import connect  # noqa: E402


def setUpModule():
    os.environ.update(isolated_data_env(str(_TMP)))
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


# The live game 83a1ec4c setup text (#87).
SETUP_TEXT = (
    "weak seed skill: Whispering Fates (F), how to identify common field herbs, often the wrong species at F, "
    "passives allow recognizing beneficial plants and avoiding poisonous ones, more powers may unlock later "
    "via practice and discovery"
)


class SkillNotesStayWithTheirSkill(unittest.TestCase):
    """#87: Whispering Fates carried Herbalism's tracking and limit."""

    def _settle(self, lines):
        opts = {
            "rank_scale": "F,E,D,C,B,A,S,SS,SSS",
            "custom_skills": SETUP_TEXT,
            "special_abilities": [{"name": "Whispering Fates", "description": "Whisper fate into the wind."}],
        }
        with connect() as conn:
            wf.ensure_world_fact_tables(conn)
            wf.clear_world_facts(conn)
            prof.clear_proficiencies(conn)
            conn.execute("DELETE FROM player_skills")
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('playthrough_options', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (json.dumps(opts),),
            )
            report = prof.apply_settlement(conn, "\n".join(lines), opts)
            rows = {r["name"]: dict(r) for r in conn.execute("SELECT name, tracking, hard_limit FROM player_proficiencies")}
            notes = {r["name"]: r["notes"] for r in conn.execute("SELECT name, notes FROM player_skills")}
        return report, rows, notes

    def test_shared_notes_stay_with_the_skill_the_text_wrote_them_for(self):
        tracking = "often the wrong species"
        limit = "passives allow recognizing beneficial plants and avoiding poisonous ones"
        for order in ((0, 1), (1, 0)):
            lines = [f"SKILL|Whispering Fates|F|{tracking}|{limit}", f"SKILL|Herbalism|F|{tracking}|{limit}"]
            report, rows, notes = self._settle([lines[i] for i in order])
            self.assertEqual(rows["Herbalism"]["tracking"], tracking, order)
            self.assertNotEqual(rows["Whispering Fates"]["tracking"], tracking, order)
            self.assertNotIn("wrong species", notes["Whispering Fates"])
            self.assertIn("wrong species", notes["Herbalism"])
            self.assertTrue(any("left unstated" in a for a in report["adjusted"]))

    def test_distinct_notes_are_untouched(self):
        report, rows, _ = self._settle([
            "SKILL|Whispering Fates|F|words that change a choice|one creature a round",
            "SKILL|Herbalism|F|often the wrong species|passives recognise plants",
        ])
        self.assertEqual(rows["Whispering Fates"]["tracking"], "words that change a choice")
        self.assertFalse(any("left unstated" in a for a in report["adjusted"]))

    def test_the_ask_says_notes_are_per_skill(self):
        self.assertIn("never give two lines the same ones", prof._SETTLE_SYSTEM)


class DutyFollowsTheClock(unittest.TestCase):
    """#83: 'off-duty guard' is a guard who is off duty now, not a job."""

    def test_pools_hold_jobs_not_states(self):
        for era in world._SEED_ROLE_POOLS.values():
            for pool in era.values():
                for role in pool:
                    self.assertNotRegex(role, r"(?i)\b(?:off|on)[\s-](?:duty|shift)\b", role)

    def test_job_of_strips_the_state(self):
        self.assertEqual(shifts.job_of("off-duty guard"), "guard")
        self.assertEqual(shifts.job_of("Off shift nurse"), "nurse")
        self.assertEqual(shifts.job_of("baker"), "baker")

    def test_guard_shift_is_seeded_stable_and_varies(self):
        a = shifts.shift_for("guard", "A", 1234)
        self.assertEqual(a, shifts.shift_for("off-duty guard", "A", 1234))
        starts = {shifts.shift_for("guard", code, 1234)[0] for code in "ABCDEFGHIJKLMNOP"}
        self.assertGreater(len(starts), 2)

    def test_on_and_off_duty_from_the_clock(self):
        start, end, _ = shifts.shift_for("baker", "B", 7)
        inside = (start + 60) % 1440
        outside = (end + 120) % 1440
        on = shifts.duty_for("baker", "B", 7, inside)
        off = shifts.duty_for("baker", "B", 7, 1440 + outside)
        self.assertTrue(on["on_duty"])
        self.assertFalse(off["on_duty"])
        self.assertIn("home", off["off_duty_likely"])
        self.assertIn("off duty", shifts.duty_note(off))

    def test_not_a_job_has_no_duty(self):
        self.assertIsNone(shifts.duty_for("patron", "C", 7, 600))
        self.assertIsNone(shifts.duty_for("local", "C", 7, 600))

    def test_story_override_expires(self):
        start, end, _ = shifts.shift_for("guard", "D", 9)
        off_minute = (end + 60) % 1440
        override = {"on_duty": True, "until": off_minute + 30, "reason": "called in early"}
        self.assertTrue(shifts.duty_for("guard", "D", 9, off_minute, override)["on_duty"])
        self.assertFalse(shifts.duty_for("guard", "D", 9, off_minute + 31, override)["on_duty"])

    def test_override_store_drops_expired(self):
        with connect() as conn:
            shifts.set_override(conn, "E", True, minutes=60, reason="covering a shift", now=1000)
            self.assertIn("E", shifts.overrides(conn, 1030))
            self.assertNotIn("E", shifts.overrides(conn, 1061))

    def test_prompt_people_carry_job_and_duty(self):
        context = {
            "current_location": {"id": 1, "name": "Gate"},
            "locations": [{
                "id": 1, "name": "Gate",
                "npcs": [{"name": "Juliana Prowse", "code": "A", "role": "off-duty guard",
                          "duty": {"on_duty": False, "shift": "22:00-06:00", "off_duty_likely": "at home asleep"}}],
            }],
        }
        person = prompts._place_view(context)["people"][0]
        self.assertEqual(person["role"], "guard")
        # A flag, not a sentence to paste (7B run 5, #83 reopened).
        self.assertIs(person["working"], False)
        self.assertNotIn("duty", person)


TEXT_T38 = (
    "You look for anything that might be useful. As you stand, you see a figure approaching from the dunes. "
    "It's a young woman, her face shadowed by a woven hood. She looks at you for a moment before turning and "
    "walking away, her steps quick and purposeful."
)


class OneFigureIsOnePerson(unittest.TestCase):
    """#73 reopened (7B T38): 'a figure ... It's a young woman' seeded Matilda and Nesta."""

    def test_a_figure_then_what_it_is_is_one_hint(self):
        self.assertEqual(world._figure_hints(TEXT_T38, ["Hargrave"]), ["a young woman"])

    def test_two_different_people_stay_two(self):
        text = "A figure waits by the gate. Later, a young woman sells bread at a stall across the square."
        self.assertEqual(len(world._figure_hints(text, [])), 2)


if __name__ == "__main__":
    unittest.main()
