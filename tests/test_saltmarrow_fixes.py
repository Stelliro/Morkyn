"""Fixes from the Saltmarrow API-bridge run (docs/showcase/saltmarrow-100-turns.md).

Each case pins one finding from docs/PLAYTEST_ISSUES.md #100-#122 or a reopened issue.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-saltmarrow-"))
_ENV = isolated_data_env(str(_TMP))
os.environ.update(_ENV)

from app import progression, prose_state, world  # noqa: E402
from app.player_resources import rest_healing  # noqa: E402

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


class LevelsComeFromXp(unittest.TestCase):
    """#121: 293 XP and still level 1, because only the model could raise a level."""

    def test_curve(self):
        self.assertEqual(progression.level_for_xp(0), 1)
        self.assertEqual(progression.level_for_xp(99), 1)
        self.assertEqual(progression.level_for_xp(100), 2)
        self.assertEqual(progression.level_for_xp(293), 2)
        self.assertEqual(progression.level_for_xp(300), 3)
        self.assertEqual(progression.level_progress(293, 2), {"level": 2, "xp": 293, "into_level": 193, "needed": 200, "next_level_at": 300})

    def test_sync_raises_and_journals_never_lowers(self):
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM player")
            conn.execute(
                "INSERT INTO player (id, name, health, max_health, level, xp, gold, karma, current_location_id) "
                "VALUES (1, 'Isk', 20, 20, 1, 320, 0, 0, 0)"
            )
            self.assertEqual(progression.sync_level(conn, 5, enabled=True), 3)
            self.assertEqual(conn.execute("SELECT level FROM player").fetchone()[0], 3)
            notes = [r[0] for r in conn.execute("SELECT content FROM journal WHERE kind = 'level_up'")]
            self.assertEqual(len(notes), 2)
            conn.execute("UPDATE player SET level = 7")
            self.assertIsNone(progression.sync_level(conn, 6, enabled=True))
            self.assertEqual(conn.execute("SELECT level FROM player").fetchone()[0], 7)
            conn.execute("UPDATE player SET level = 1, xp = 900")
            self.assertIsNone(progression.sync_level(conn, 7, enabled=False))


class SleepHeals(unittest.TestCase):
    """#120: 13 and 17 hours of sleep healed nothing."""

    def test_amounts(self):
        self.assertEqual(rest_healing(minutes=817, kind="sleep", health=9, max_health=20), 6)
        self.assertEqual(rest_healing(minutes=120, kind="sleep", health=9, max_health=20), 1)
        self.assertEqual(rest_healing(minutes=480, kind="meditate", health=9, max_health=20), 2)
        self.assertEqual(rest_healing(minutes=600, kind="wait", health=9, max_health=20), 0)
        self.assertEqual(rest_healing(minutes=900, kind="sleep", health=19, max_health=20), 1)


class NamedCoinIsExact(unittest.TestCase):
    """#69/#96 reopened: spelled sums the op and prose agree on were re-rolled."""

    def _settle(self, gold, narration, line):
        result = {"narration": narration, "player": {"gold_delta": gold}}
        note = world._settle_stated_gold(result, line)
        return result["player"].get("gold_delta"), note

    def test_mentions(self):
        self.assertEqual(prose_state.coin_mentions("Nine coins. All you had."), [9])
        self.assertEqual(prose_state.coin_mentions("three coins, then 2 gold"), [3, 2])

    def test_loss_named_without_paying_verb(self):
        value, note = self._settle(-9, "He takes the purse. Nine coins. All you had.", "Take my purse.")
        self.assertEqual(value, -9)
        self.assertEqual(note["source"], "stated_mention")

    def test_modest_gain_named(self):
        value, _ = self._settle(9, "Tam holds out your own purse. It clinks. Nine coins.", "I wait.")
        self.assertEqual(value, 9)

    def test_large_or_unnamed_gain_still_rolls(self):
        self.assertIsNone(self._settle(250, "The reeve gives you 250 gold.", "I wait.")[1])
        self.assertIsNone(self._settle(9, "Tam gives you your purse back.", "I wait.")[1])

    def test_put_down_is_an_offer(self):
        self.assertEqual(prose_state.player_trade_offer("I put three coin on the counter for the rope."), 3)
        self.assertEqual(prose_state.stated_coin_amounts("You count three coins out of your purse.")["paid"], [3])


class NameRepairLeavesSentencesAlone(unittest.TestCase):
    """#107: "Tam Kemp [[H]] Turn and wedge" and "H. says" became another name."""

    NAMES = {"H": "Hereward", "T": "Tam Kemp"}

    def _repair(self, text):
        from app import llm

        return llm._repair_prose_entity_labels(text, self.NAMES)

    def test_capital_order_untouched(self):
        out = self._repair("Hereward [[H]] points at the cleat. Turn and wedge.")
        self.assertIn(". Turn and wedge.", out)
        self.assertNotIn("Tam Kemp Turn", out)

    def test_quoted_line_untouched(self):
        out = self._repair('Hereward [[H]] shrugs. "Ask her. says the harbour."')
        self.assertIn('"Ask her. says the harbour."', out)

    def test_initial_untouched(self):
        out = self._repair("The ledger is signed H. says nothing more.")
        self.assertNotIn("Tam Kemp says", out)
        self.assertNotIn("Hereward says", out)

    def test_real_hole_still_filled(self):
        out = self._repair("The rope goes slack. — leans against the rail.")
        self.assertRegex(out, r"(Hereward|Tam Kemp) leans against")


class TravelSceneIsNotCut(unittest.TestCase):
    """#111: a rowing trip was cut back to "You take the stern"."""

    LINE = "Mam and I go down the harbour stairs to Hereward's skiff, and he rows us out to the customs tower."

    def test_take_a_position_is_not_taking(self):
        from app import llm

        self.assertEqual(llm._invented_unit_family("You take the stern.", self.LINE, self.LINE), "")
        self.assertEqual(llm._invented_unit_family("You take the bread.", "I ask about bread", "I ask about bread"), "taking")

    def test_travel_line_keeps_the_scene(self):
        from app import llm

        narration = (
            "Hereward [[H]] unties the skiff. You take the stern. " * 6
            + "The tower rises out of the grey. A clerk asks for your name and you give it."
        )
        out = llm._cut_scene_at_invented_request({"narration": narration, "self_check": {}}, self.LINE)
        self.assertFalse(out.get("_scene_cut"))
        self.assertEqual(out["narration"], narration)


class ChecksReadThePlayersLine(unittest.TestCase):
    """#89 reopened, #102: the engine's own note rolled persuasion every turn; keywords misread acts."""

    NOTE = (
        "\n\nResolved player references: Conversation (engine decided) - the player is talking to "
        "Tam Kemp [[H]]. Only Tam Kemp [[H]] answers the player."
    )

    def _skill(self, line, context=None):
        from app.skill_checks import infer_check_from_action

        check = infer_check_from_action(line, context or {})
        return check and check["skill_code"]

    def test_engine_note_rolls_nothing(self):
        line = "Tam and I set the iron bar against the bollard and walk the line round it a turn at a time."
        self.assertIsNone(self._skill(line + self.NOTE))
        self.assertIsNone(self._skill("I step back out onto the wall and head out along the deep channel." + self.NOTE))

    def test_keyword_misreads(self):
        self.assertIsNone(self._skill("I lie flat and crawl up the ramp on my belly."))
        self.assertIsNone(self._skill("I tie the rope round Tam's waist, then round mine."))
        self.assertIsNone(self._skill("\"No cart's worth you.\""))
        self.assertIsNone(self._skill("I stay by the board and wait. I'm not hiding."))
        self.assertIsNone(self._skill("I strike the flint over the wick until it catches."))
        self.assertIsNone(self._skill("I climb into the skiff beside Hereward."))
        self.assertIsNone(self._skill("I keep hold of the rope and watch how fast the water climbs the tiles."))

    def test_real_acts_still_roll(self):
        self.assertEqual(self._skill("I strike him with my staff"), "melee")
        self.assertEqual(self._skill("he strikes at the guard"), "melee")
        self.assertEqual(self._skill("I lie to the reeve about the cart"), "deception")
        self.assertEqual(self._skill("what is the ring worth?"), "appraise")
        self.assertEqual(self._skill("I mine for iron"), "mining")
        self.assertEqual(self._skill("I climb the sea wall"), "athletics")
        self.assertEqual(self._skill("I don't wait and hide behind the crates"), "stealth")

    def test_opponent_is_the_addressee_not_a_listener(self):
        from app.skill_checks import infer_check_from_action

        people = [{"code": "K", "name": "Mara Tarrow"}, {"code": "H", "name": "Tam Kemp"}]
        ctx = {"npcs": people, "conversation_turn": {"addressed": ["H"]}}
        check = infer_check_from_action("I ask him which channel he took.", ctx)
        self.assertEqual(check["opposition"]["name"], "Tam Kemp")
        named = infer_check_from_action("I ask Mara which channel Tam took.", ctx)
        self.assertEqual(named["opposition"]["name"], "Mara Tarrow")
        nobody = infer_check_from_action("I ask which channel he took.", {"npcs": people})
        self.assertIsNone(nobody["opposition"])


class AddresseeFromTheLine(unittest.TestCase):
    """#104: roles, surnames, kinship words and no-talk lines."""

    TAM = {"id": 1, "code": "H", "name": "Tam Kemp", "role": "carter"}
    MARA = {"id": 2, "code": "K", "name": "Mara Tarrow", "role": "tide-reader"}
    CLERK = {"id": 3, "code": "B", "name": "Hereward Jessop", "role": "clerk"}
    WEAVER = {"id": 4, "code": "C", "name": "Wulfstan", "role": "weaver"}
    REEVE = {"id": 5, "code": "N", "name": "Baldwin Thorne", "role": "reeve"}

    def _resolve(self, npcs, line, target):
        import json

        from app import conversation as cv

        codes = [n["code"] for n in npcs]
        state = {"target": [target], "why": "last_speaker", "present": codes, "here": codes}
        ctx = {
            "current_location": {"id": 1, "code": "L1"},
            "locations": [{"id": 1, "code": "L1", "npcs": npcs}],
            "settings": {"conversation": json.dumps(state)},
        }
        r = cv.resolve(ctx, line)
        return r["addressed"], r["rule"]

    def test_role_names_the_one_who_holds_it(self):
        line = 'I cross to the tide clerk at the wall. "Why\'d you move the dry tide?"'
        self.assertEqual(self._resolve([self.WEAVER, self.CLERK], line, "C"), (["B"], "name"))

    def test_shared_role_names_nobody(self):
        other = {"id": 6, "code": "D", "name": "Una Rendle", "role": "tally clerk"}
        line = "I ask the clerk what the bell pays."
        self.assertNotEqual(self._resolve([self.CLERK, other, self.WEAVER], line, "C")[1], "name")

    def test_title_and_surname(self):
        line = "I hold the page out to Reeve Thorne. \"Read it to them.\""
        self.assertEqual(self._resolve([self.CLERK, self.REEVE], line, "B"), (["N"], "name"))

    def test_kinship_word_is_not_the_last_partner(self):
        self.assertEqual(self._resolve([self.TAM, self.MARA], '"Six years, Mam. Why didn\'t you come home?"', "H"), ([], "none"))

    def test_no_talk_no_addressee(self):
        line = "Tam and I set the iron bar against the bollard and walk the line round it."
        self.assertEqual(self._resolve([self.TAM, self.MARA], line, "H"), ([], "none"))
        line = "I get Tam's arm over my shoulder. At the top I look for Philippa in the crowd."
        self.assertEqual(self._resolve([self.TAM, self.MARA], line, "H"), ([], "none"))

    def test_vocative_and_question_still_talk(self):
        self.assertEqual(self._resolve([self.TAM, self.MARA], "Tam, come with me.", "K"), (["H"], "name"))
        self.assertEqual(self._resolve([self.TAM, self.MARA], "Which channel did he take?", "K")[0], ["K"])


class PeopleMoveWithThePlayer(unittest.TestCase):
    """#105: Tam carried to the roof stayed at the market; the skiff's passengers stayed at the tower."""

    PEOPLE = [
        {"code": "H", "name": "Tam Kemp"},
        {"code": "B", "name": "Hereward Jessop"},
        {"code": "A", "name": "Philippa Kemp"},
    ]

    def _with(self, line):
        from app import scene_thread as st

        return [p["code"] for p in st.going_with(line, self.PEOPLE)]

    def test_the_line_takes_them_along(self):
        self.assertEqual(self._with("I get Tam's arm over my shoulder and we go up the stairs together."), ["H"])
        self.assertEqual(self._with("I carry Tam up the ladder onto the roof."), ["H"])
        self.assertEqual(self._with("Philippa and I walk to the market."), ["A"])
        self.assertEqual(self._with("I go down to Hereward's skiff, and he rows us out to the tower."), ["B"])

    def test_not_along(self):
        self.assertEqual(self._with("I leave Tam at the stall and walk to the tower."), [])
        self.assertEqual(self._with("At the top I look for Philippa in the crowd."), [])
        self.assertEqual(self._with('I walk to the tower. "Tam, we go together," I said.'), [])

    def test_cast_present_and_shown_moves_the_record(self):
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM player")
            conn.execute("DELETE FROM npcs WHERE code IN ('H', 'K')")
            conn.execute(
                "INSERT INTO player (id, name, health, max_health, level, xp, gold, karma, current_location_id) "
                "VALUES (1, 'Isk', 20, 20, 1, 0, 0, 0, 2)"
            )
            conn.execute("INSERT INTO npcs (code, name, location_id) VALUES ('H', 'Tam Kemp', 7)")
            conn.execute("INSERT INTO npcs (code, name, location_id) VALUES ('K', 'Mara Tarrow', 7)")
            moved = world._move_cast_here(conn, {"present": ["H", "K"]}, "Tam [[H]] climbs out of the skiff behind you.")
            self.assertEqual(moved, ["Tam Kemp"])
            where = dict(conn.execute("SELECT code, location_id FROM npcs WHERE code IN ('H', 'K')").fetchall())
            self.assertEqual(where, {"H": 2, "K": 7})


class OpsNameThePlayerAndNewPeople(unittest.TestCase):
    """#106: REL to YOU became the code YOU; CAST could not name someone made this turn."""

    def test_transcoder(self):
        from app import turn_dsl

        ops = turn_dsl.parse_ops(
            'REL K YOU "her daughter, gone six years"\n'
            'REL "Mara Tarrow" [[H]] "the boy who signed first"\n'
            'CAST present "Mara Tarrow"\n'
            "CAST interacting [[H]] Tam\n"
        )
        turn = turn_dsl.ops_to_turn("Mara Tarrow [[K]] looks at you.", ops)
        rels = [(r["source_code"], r["target_code"]) for r in turn["relationships"]]
        self.assertEqual(rels, [("K", "PLAYER"), ("Mara Tarrow", "H")])
        self.assertEqual(turn["scene_cast"]["present"], ["Mara Tarrow"])
        self.assertEqual(turn["scene_cast"]["interacting"], ["H"])

    def test_bond_and_kin_alias_and_cast_by_name(self):
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM player")
            conn.execute("DELETE FROM npcs WHERE code IN ('K', 'H')")
            conn.execute("DELETE FROM aliases WHERE entity_code = 'K'")
            conn.execute(
                "INSERT INTO player (id, name, health, max_health, level, xp, gold, karma, current_location_id) "
                "VALUES (1, 'Isk', 20, 20, 1, 0, 0, 0, 2)"
            )
            conn.execute("INSERT INTO npcs (code, name, location_id, known_facts) VALUES ('K', 'Mara Tarrow', 2, '[]')")
            conn.execute("INSERT INTO npcs (code, name, location_id, known_facts) VALUES ('H', 'Tam Kemp', 2, '[]')")
            world._apply_relationships(conn, [{"source_code": "K", "target_code": "PLAYER", "summary": "her daughter Isk; Mara is the player's mother"}])
            facts = conn.execute("SELECT known_facts FROM npcs WHERE code = 'K'").fetchone()[0]
            self.assertIn("To the player: her daughter Isk", facts)
            aliases = {r[0] for r in conn.execute("SELECT alias FROM aliases WHERE entity_code = 'K'")}
            self.assertIn("Mam", aliases)
            cast = {"present": ["Mara Tarrow"], "interacting": []}
            world._apply_scene_cast(conn, cast, "Mara Tarrow [[K]] nods.")
            self.assertEqual(cast["present"], ["K"])


class PacketsCarryTheCharacter(unittest.TestCase):
    """#100: the opening packet had no character; #101: ability use said nothing of what it does."""

    CTX = {
        "player": {"name": "Isk Tarrow", "title": "Flat-runner", "health": 20, "max_health": 20},
        "inventory": [
            {"name": "patched tunic", "code": "I2", "equipped_slot": "TORSO", "quantity": 1},
            {"name": "mother's brass tide-reckoner", "code": "I4", "equipped_slot": "", "quantity": 1},
            {"name": "spent rope", "code": "I5", "equipped_slot": "", "quantity": 0},
        ],
        "abilities": [{"code": "AB1", "name": "Tidecount", "description": "Feels the water's return. Knows which channels fill first.", "cost": "1 energy"}],
        "skills": [{"name": "Salvage", "value": 3, "notes": "Start rank E; grows with each haul"}, {"name": "Deception", "value": 0}],
        "settings": {"playthrough_options": {"character_backstory": "Isk runs the flats. Her mother never came back.", "custom_style": "A harbour the sea left."}},
    }

    def test_opening_has_the_sheet(self):
        from app import prompts

        player = prompts._visible_world(self.CTX, "__opening_scene_request__: begin")["player"]
        self.assertEqual([i["name"] for i in player["carried"]], ["mother's brass tide-reckoner"])
        self.assertEqual(player["abilities"][0]["does"], "Feels the water's return.")
        self.assertEqual(player["trained_in"], ["Salvage (E)"])
        self.assertIn("Her mother never came back.", player["backstory"])
        self.assertEqual(player["premise"], "A harbour the sea left.")

    def test_later_turns_skip_the_backstory(self):
        from app import prompts

        player = prompts._visible_world(self.CTX, "I look at the tide.")["player"]
        self.assertNotIn("backstory", player)
        self.assertNotIn("abilities", player)

    def test_ability_use_names_it_and_says_what_it_does(self):
        from app import prompts
        from app.player_resources import ability_use_prompt_block

        mech = {"ability_use": {"ok": True, "ability": "Tidecount", "description": "Feels the water's return."}}
        view = prompts._mechanics_view({"mechanics_context": mech})["ability_use"]
        self.assertEqual((view["name"], view["does"]), ("Tidecount", "Feels the water's return."))
        block = ability_use_prompt_block({"ability": "Tidecount", "description": "Feels the water's return.", "cost": {}})
        self.assertIn("What it does: Feels the water's return.", block)


if __name__ == "__main__":
    unittest.main()
