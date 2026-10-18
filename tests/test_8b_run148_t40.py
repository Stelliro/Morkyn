"""8B run 148, T40: one walk to the tally house, three faults.

"I climb back onto the planks and look along the shore for where the hooded
figure went, then walk to the Salvage Guild's Tally House to report that the
wreck has been picked clean." The prose arrived at the door and went inside.

  * The act "climb" finished the step "Salvage the wreck": the matcher read
    "salvage" and "wreck" from the walk clause as the climb's objects.
  * The move ended in the town square ("entered from Saltmarrow; the journey
    ends there") because The Docks stand under the harbour, not the town.
  * NPC_NEW "Gideon" ROLE "Salvage Guild clerk" LOC the tally house minted a
    second clerk beside Griselda Kemp, filed there, and took "the hooded
    figure" as his alias although that figure "has vanished".

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run148_t40
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-run148-t40-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


LINE = ("I climb back onto the planks and look along the shore for where the hooded figure went, then walk to the "
        "Salvage Guild's Tally House to report that the wreck has been picked clean.")
PROSE = (
    "The planks creak under your weight as you climb up, your breath sharp with the morning air. You scan the "
    "shoreline, the waves lapping at the sand, but the hooded figure has vanished. No trace of them, just the "
    "lingering scent of salt and rust. You turn toward the Salvage Guild’s Tally House, its weathered sign creaking "
    "in the breeze. The walk is short, the path worn smooth by countless feet, and you arrive at the building’s "
    "door, its frame splintered and splattered with grime.\n\nInside, the air is thick with the smell of oil and old "
    "parchment. A few figures huddle around a table, their faces shadowed by the dim light. One looks up as you "
    "enter, their gaze sharp. “You’re late,” they say, their voice rough with disapproval. “The wreck’s been picked "
    "clean, then?” The man leans forward, his fingers tapping a rhythm on the table."
)
QUEST = {
    "id": 2, "code": "Q2", "title": "Salvage the Stormbreaker", "status": "active", "current_step": 2,
    "total_steps": 4, "steps": [
        {"step_number": 1, "title": "Find the wreck of the Stormbreaker in the northern docks.", "description": ""},
        {"step_number": 2, "title": "Salvage the wreck.", "description": ""},
    ],
}


class TheActsOwnClause(unittest.TestCase):
    def test_a_climb_does_not_salvage_the_wreck_named_in_the_next_clause(self):
        from app.quests import match_quest_step

        self.assertIsNone(match_quest_step(LINE, [dict(QUEST)], location_code="L11"))

    def test_the_salvage_itself_still_does(self):
        from app.quests import match_quest_step

        line = "I dive on the wreck at low water and salvage what I can from the hull, keeping an eye on the tide."
        match = match_quest_step(line, [dict(QUEST)], location_code="L11")
        self.assertIsNotNone(match)
        self.assertEqual(match["code"], "Q2")

    def test_lashing_the_hull_secures_the_wreck(self):
        # T73: "drive the last wedge ... and lash the final line tight so the wreck is secured" rolled no step.
        from app.prose_state import act_rules
        from app.quests import match_quest_step

        line = ("I drive the last wedge into the hull with the mallet and lash the final line tight so the wreck is secured "
                "against the tide.")
        act = act_rules(line)
        self.assertIsNotNone(act)
        self.assertEqual(act["family"], "secure")
        quest = {**QUEST, "current_step": 3, "steps": QUEST["steps"] + [
            {"step_number": 3, "title": "Secure the wreck to prevent further damage.", "description": ""}]}
        match = match_quest_step(line, [quest], location_code="L8")
        self.assertIsNotNone(match)
        self.assertEqual(match["step_number"], 3)

    def test_starting_the_dive_is_the_dive(self):
        # 8B run 149, T5: "start the dive the guild asked for" read no act and rolled persuasion.
        from app.prose_state import act_rules

        act = act_rules("I wade out into the Dredges at low tide and start the dive the guild asked for, reckoner in hand.")
        self.assertIsNotNone(act)
        self.assertEqual(act["family"], "swim")
        self.assertIsNone(act_rules("I look over the dive gear on the bench and ask its price."))

    def test_an_act_in_a_later_clause_keeps_its_own_words(self):
        from app.quests import _act_clause

        own = "I thank Godfrey, then polish the swords on the rack for Finnian"
        self.assertEqual(_act_clause(own, {"polish", "polishes", "polished", "polishing"}), "polish the swords on the rack for Finnian")
        self.assertEqual(_act_clause("I polish the swords", {"polish"}), "I polish the swords")


def _world():
    from app import world
    from app.db import connect, init_db

    init_db()
    world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
    with connect() as conn:
        town = int(conn.execute("SELECT current_location_id FROM player").fetchone()[0])
        tally = int(world._upsert_location(conn, "The Salvage Guild's Tally House", "", parent_id=town, kind=""))
        conn.execute("INSERT INTO locations (code, name, summary) VALUES ('L90', 'The Harbour', '')")
        harbour = int(conn.execute("SELECT id FROM locations WHERE code = 'L90'").fetchone()[0])
        conn.execute("INSERT INTO locations (code, name, summary, parent_id) VALUES ('L91', 'The Docks', '', ?)", (harbour,))
        docks = int(conn.execute("SELECT id FROM locations WHERE code = 'L91'").fetchone()[0])
        conn.execute("DELETE FROM npcs")
        conn.execute(
            "INSERT INTO npcs (code, location_id, name, race, role, summary, attitude) VALUES ('B', ?, 'Griselda Kemp', 'human', 'clerk', '', 'neutral')",
            (tally,),
        )
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (docks,))
    return town, tally, docks


class TheProseEntersTheTallyHouse(unittest.TestCase):
    def test_the_walk_from_the_docks_ends_inside(self):
        from app import world
        from app.db import connect

        town, tally, docks = _world()
        with connect() as conn:
            result = {"narration": PROSE, "player": {"move_to_location": "The Salvage Guild’s Tally House"}}
            report = world.resolve_movement(conn, result, LINE, intent="travel", narration=PROSE)
            self.assertEqual(report.get("status"), "model", report)
            world._apply_player(conn, result["player"])
            now = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])
        self.assertEqual(now, tally, (town, docks, report))


class TheClerkAtTheOpsPlace(unittest.TestCase):
    def test_a_new_clerk_filed_at_the_tally_house_is_griselda(self):
        from app import world
        from app.db import connect

        _world()
        npcs = [{"name": "Gideon", "role": "Salvage Guild clerk", "location": "The Salvage Guild’s Tally House"}]
        with connect() as conn:
            out = world._npcs_shown_in_prose(conn, npcs, PROSE)
        self.assertEqual([n.get("name") for n in out], ["Griselda Kemp"], out)

    def test_a_vanished_figure_is_no_one_to_bind(self):
        from app import world
        from app.db import connect

        _world()
        with connect() as conn:
            conn.execute("DELETE FROM npcs")
        npcs = [{"name": "Gideon", "role": "Salvage Guild clerk", "location": "The Salvage Guild’s Tally House"}]
        with connect() as conn:
            out = world._npcs_shown_in_prose(conn, npcs, PROSE)
        self.assertFalse(any("hooded" in str(n.get("_bound_hint") or "") for n in out), out)

    def test_the_gone_sentence_shapes(self):
        from app.world import _figure_gone

        self.assertTrue(_figure_gone("You look up, but the hooded figure has vanished. No trace of them.", "the hooded figure"))
        self.assertTrue(_figure_gone("The cloaked man is nowhere to be seen when you turn.", "The cloaked man"))
        self.assertFalse(_figure_gone("The cloaked man steps closer, his hand out.", "The cloaked man"))


class AGuildIsNoPerson(unittest.TestCase):
    """8B run 149, T2: NPC_NEW "The Salvage Guild" ROLE "guild authority" drew a person named Bertha for the guild."""

    PROSE = ("“Thirty gold,” he says. “You answer to the guild. They’ll be waiting for you at the docks.” His gaze flicks to "
             "the open ledger on his desk.")

    def test_the_guild_is_dropped(self):
        from app import world
        from app.db import connect

        _world()
        with connect() as conn:
            out = world._npcs_shown_in_prose(
                conn, [{"name": "The Salvage Guild", "role": "guild authority", "location": "docks"}], self.PROSE)
        self.assertEqual(out, [])

    def test_a_guild_clerk_is_a_person(self):
        from app.world import _GROUP_NAME_RE

        self.assertFalse(_GROUP_NAME_RE.search("Griselda Kemp"))
        self.assertFalse(_GROUP_NAME_RE.search("the guild clerk"))
        self.assertTrue(_GROUP_NAME_RE.search("The Harbour Reeves"))


class TheScarredManIsBertram(unittest.TestCase):
    """T69-T70: "the scarred man" minted Garret, then Kael, beside Bertram Northcott, "a burly man with a scar across his brow"."""

    PROSE = ("You take the scarred man and two others, and you walk down to the wreck with the mallet and the line. "
             "The scarred man sets the mallet down and begins to lash the line around the hull, his movements sure and "
             "practiced. The younger man helps, tying the knots.")

    def _with_bertram(self):
        from app.db import connect

        town, tally, docks = _world()
        with connect() as conn:
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, race, role, summary, attitude, known_facts) VALUES "
                "('M', ?, 'Bertram Northcott', 'human', 'dock hand', 'Their leader, a burly man with a scar across his brow, steps forward.', 'neutral', '[]')",
                (docks,),
            )

    def test_the_scarred_man_is_the_known_scarred_man(self):
        from app import world
        from app.db import connect

        self._with_bertram()
        with connect() as conn:
            out = world._npcs_shown_in_prose(conn, [{"name": "Kael", "role": "dock worker"}], self.PROSE)
        self.assertEqual([n.get("name") for n in out], ["Bertram Northcott"], out)

    def test_two_scarred_men_known_bind_nobody(self):
        from app import world
        from app.db import connect

        self._with_bertram()
        with connect() as conn:
            docks = int(conn.execute("SELECT location_id FROM npcs WHERE code = 'M'").fetchone()[0])
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, race, role, summary, attitude, known_facts) VALUES "
                "('N', ?, 'Garret', 'human', 'dock hand', 'a fellow with a scar from temple to jaw', 'neutral', '[]')",
                (docks,),
            )
            out = world._npcs_shown_in_prose(conn, [{"name": "Kael", "role": "dock worker"}], self.PROSE)
        self.assertNotIn("Bertram Northcott", [n.get("name") for n in out])


if __name__ == "__main__":
    unittest.main()
