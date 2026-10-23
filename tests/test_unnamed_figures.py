"""Unnamed NPCs are stored and numbered per kind (Stell, 2026-10-24; app/unnamed.py).

"hostile monster npc's should also be stored in the database, they should be
provided an increasing id intiger per appearing non named npc". Before this, a
creature was never a row: the person-or-place ask answered "place" for one, and
the figure hints only knew person words, so cc87dd29 T2 ("set off to New Vegas
to fight a Deathclaw") and the offline game a1fedf99 ("a group of 4 ghouls
BRUTALLY attack me") left nothing to attack. The strings below are the run's
own where it has them (the T2 line and prose, the a1fedf99 line put in the
narrator's mouth); the rest are the shapes the decision names. The mocked asks
answer on their first word, as Hermes 3 8B did on every small ask measured.
"""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-unnamed-"))
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


T2_LINE = "i get in my power armor, grab my minigun, and set off to New Vegas to fight a Deathclaw"
# cc87dd29 T2 as shipped (final_turn.narration, codes stripped): the Deathclaw
# is a target two miles west, never in the scene.
T2_PROSE = (
    "You stride purposefully towards New Vegas, the minigun cradled in your armored fist, when a sudden ping from "
    "your power armor's readouts pulls you up short. A new message blinks into existence: \"New target detected. "
    "2 miles west. Priority high.\" Your gaze swings automatically to the west, tracking the direction of the "
    "threat.\n\nYou trudge onwards, the minigun held ready in your armored grip, when suddenly the power armor's "
    "readouts ping a priority alert. A flashing arrow points 2 miles west, towards a new Deathclaw target lurking in "
    "the ruins. The decision presses - continue to New Vegas or investigate this closer threat first?"
)
# The scene T2 set up, played out: the Deathclaw is here.
DEATHCLAW_PROSE = "A Deathclaw bursts from the ruins and charges at you, claws raking the asphalt."
# a1fedf99 T6, the player's "a group of 4 ghouls BRUTALLY attack me", as the narrator would write it.
GHOULS_LINE = "a group of 4 ghouls BRUTALLY attack me"
GHOULS_PROSE = "A group of 4 ghouls brutally attack you, clawing and snapping as they close in."
# cc87dd29 T3 (final_turn.narration, codes stripped).
T3_PROSE = (
    "You confidently stride into the bustling Radiation Fenced Sanctuary clinic, ready to deal with the staff. The air "
    "is thick with the scent of antiseptic and filled with urgent conversation. At the front desk, a nurse in a blue "
    "helmet looks up at you. \"You here for treatment or just browsing the wares?\" she asks, her voice tinged with "
    "annoyance. The nurse sighs and points to a curtained-off area in the back."
)
# The baseline replay's opening (live/baseline/turns/000.json).
BASELINE_T0 = (
    "It is morning. The sun's rays filter through a haze of radioactive particles, casting an eerie glow over "
    "Radiation Fenced Sanctuary. The settlement is more of a proper sanctuary than a cluster of ramshackle buildings. "
    "A few people move between the open fronts of shops, haggling over goods. The air is thick with the scent of "
    "sweat and ozone."
)


def _fresh_world():
    from app import db, rng, world

    db.init_db()
    rng.reset_seed_cache()
    world.start_playthrough({"player_name": "Will Tanaka", "start_location": "Radiation Fenced Sanctuary",
                             "special_ability_origin": "none"})


class _Asker:
    """The model, scripted: figure_kind yes for the nouns given, figure_hostile per noun; every call kept."""

    def __init__(self, figures=(), hostile=(), entity_kind="person"):
        self.figures = {f.lower() for f in figures}
        self.hostile = {h.lower() for h in hostile}
        self.entity_kind = entity_kind
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system, user, *, trace=None, usage=None, phase="", max_tokens=None):
        self.calls.append((phase, user))
        if phase == "figure_kind":
            return "Yes." if any(f'is "{f}" a person' in user for f in self.figures) else "No."
        if phase == "figure_hostile":
            return "Yes" if any(h in user.lower() for h in self.hostile) else "No"
        if phase == "entity_kind":
            return self.entity_kind
        if phase == "quote_speaker":
            return "yes"
        return "no"

    def asked(self, phase):
        return [user for p, user in self.calls if p == phase]


def _play(prose, line, asker, ops='SUMMARY: "A scene."'):
    """Parse the draft, settle before apply_turn as play_turn does, then apply."""
    from app import entity_kinds, world
    from app.turn_dsl import parse_dsl_turn

    turn = parse_dsl_turn(f"===NAR===\n{prose}\n\n===OPS===\n{ops}\n", line)
    turn["narration"] = prose
    previous = entity_kinds.set_kind_ask(asker)
    try:
        entity_kinds.settle_kinds(turn, line)
        world.apply_turn(turn, line, input_kind="player")
    finally:
        entity_kinds.set_kind_ask(previous)
    return turn


def _rows(where="kind != ''"):
    from app import db

    with db.connect().closing() as conn:
        return [dict(r) for r in conn.execute(
            f"SELECT id, code, name, role, attitude, race, kind, kind_number, location_id, died_turn FROM npcs "
            f"WHERE {where} ORDER BY id"
        ).fetchall()]


def _names(where="kind != ''"):
    return [r["name"] for r in _rows(where)]


class Words(unittest.TestCase):
    """The kind is the text's own head noun, singular and title case: read, not listed."""

    def test_the_head_noun_and_its_count(self):
        from app import unnamed

        def read(text):
            return [(m["kind"], m["form"], m["count"], m["ordinal"]) for m in unnamed.mentions(text)]

        self.assertEqual(read(GHOULS_PROSE), [("ghoul", "count", 4, 0)])
        self.assertEqual(read(DEATHCLAW_PROSE), [("deathclaw", "count", 1, 0)])
        self.assertEqual(read("A rotting ghoul lunges at you."), [("ghoul", "count", 1, 0)])
        self.assertEqual(read("Two raiders step out from behind the wreck and level their rifles at you."),
                         [("raider", "count", 2, 0)])
        self.assertEqual(read("A second ghoul drops from the ceiling behind you."), [("ghoul", "ordinal", 0, 2)])
        self.assertEqual(read("Another ghoul crawls out of the vent."), [("ghoul", "another", 1, 0)])
        self.assertEqual(read("The raider snarls at you."), [("raider", "the", 0, 0)])
        self.assertEqual(read("A guard in a dented helmet steps in front of you."), [("guard", "count", 1, 0)])
        # An unstated plural is two, the least a plural can be.
        self.assertEqual(read("A pack of wolves circles you."), [("wolf", "count", 2, 0)])
        self.assertEqual(read("Some ghouls shamble toward you."), [("ghoul", "count", 2, 0)])
        # A named one is no unnamed figure; quoted speech is never read.
        self.assertEqual(read("A raider named Kade levels his rifle at you."), [])
        self.assertNotIn("ghoul", [k for k, *_ in read('"A ghoul attacked me," the guard says.')])

    def test_kind_names(self):
        from app import unnamed

        self.assertEqual([unnamed.kind_title(w) for w in ("ghouls", "Deathclaw", "wolves", "men", "zombies", "raiders")],
                         ["Ghoul", "Deathclaw", "Wolf", "Man", "Zombie", "Raider"])

    def test_an_op_name_that_is_only_a_kind(self):
        from app import unnamed

        self.assertEqual(unnamed.op_kind("Ghoul", "A ghoul lunges at you. The ghoul hisses."), "Ghoul")
        # A name the prose uses bare is a name.
        self.assertEqual(unnamed.op_kind("Stone", "Stone [[B]] nods at the stone wall."), "")
        self.assertEqual(unnamed.op_kind("Beth", "Beth looks up from her desk."), "")


class Numbered(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_t2_prose_files_no_deathclaw_but_the_scene_with_one_does(self):
        # T2 as shipped: the Deathclaw is a target two miles off. Nothing is
        # numbered, and the person-or-place verdicts are untouched.
        asker = _Asker(figures=("deathclaw",), hostile=("deathclaw",), entity_kind="place")
        _play(T2_PROSE, T2_LINE, asker)
        self.assertEqual(_names(), [])
        self.assertNotIn("New Vegas", _names("1 = 1"))
        # The scene with the Deathclaw in it: a person row, numbered, hostile.
        asker = _Asker(figures=("deathclaw",), hostile=("deathclaw",))
        _play(DEATHCLAW_PROSE, "i fight the Deathclaw", asker)
        rows = _rows()
        self.assertEqual([(r["name"], r["kind"], r["kind_number"], r["attitude"]) for r in rows],
                         [("Deathclaw 1", "Deathclaw", 1, "hostile")])
        self.assertEqual(rows[0]["race"], "unknown")
        self.assertRegex(rows[0]["code"], r"^[A-Z]{1,3}$")
        self.assertEqual(len(asker.asked("figure_kind")), 1)
        self.assertIn('is "deathclaw" a person, an animal or a monster?', asker.asked("figure_kind")[0])

    def test_a_noun_the_ask_says_is_no_figure_is_not_filed(self):
        asker = _Asker(figures=())
        _play("A cold wind bites at your face as you climb.", "i climb", asker)
        self.assertEqual(_names(), [])
        self.assertEqual(len(asker.asked("figure_kind")), 1)

    def test_a_group_of_4_ghouls_is_four_rows(self):
        asker = _Asker(figures=("ghoul",), hostile=("ghoul",))
        _play(GHOULS_PROSE, GHOULS_LINE, asker)
        rows = _rows()
        self.assertEqual([r["name"] for r in rows], ["Ghoul 1", "Ghoul 2", "Ghoul 3", "Ghoul 4"])
        self.assertEqual(len({r["code"] for r in rows}), 4)
        self.assertEqual({r["attitude"] for r in rows}, {"hostile"})
        # They stay four after the sketch pass (no twin collapse).
        self.assertEqual(len(_rows("kind = 'Ghoul'")), 4)

    def test_a_second_ghoul_in_a_later_turn(self):
        _play("A rotting ghoul lunges at you from the shadows.", "i look around", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        asker = _Asker(figures=(), hostile=("ghoul",))
        _play("A second ghoul drops from the ceiling behind you.", "i back away", asker)
        self.assertEqual(_names(), ["Ghoul 1", "Ghoul 2"])
        # The kind is the save's record now: no kind ask.
        self.assertEqual(asker.asked("figure_kind"), [])
        asker = _Asker()
        _play("Another ghoul crawls out of the vent toward you.", "i run", asker)
        self.assertEqual(_names(), ["Ghoul 1", "Ghoul 2", "Ghoul 3"])

    def test_the_ghoul_is_the_one_here(self):
        _play("A rotting ghoul lunges at you from the shadows.", "i look around", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        _play("The ghoul staggers back, hissing at you.", "i kick it away", _Asker())
        self.assertEqual(_names(), ["Ghoul 1"])
        from app import db

        with db.connect().closing() as conn:
            scene = json.loads(conn.execute("SELECT value FROM settings WHERE key = 'active_scene'").fetchone()[0])
        self.assertIn(_rows()[0]["code"], scene.get("present") or [])
        # And "a ghoul" told again with that one here is that ghoul (resolve before minting).
        _play("A ghoul claws at your boots.", "i stamp", _Asker())
        self.assertEqual(_names(), ["Ghoul 1"])

    def test_two_raiders_then_the_raider_mints_nothing(self):
        _play("Two raiders step out from behind the wreck and level their rifles at you.", "i freeze",
              _Asker(figures=("raider",), hostile=("raider",)))
        self.assertEqual(_names(), ["Raider 1", "Raider 2"])
        from unittest import mock

        from app import unnamed

        with mock.patch.object(unnamed.turn_ledger, "note") as note:
            _play("The raider snarls at you.", "i raise my hands", _Asker())
        self.assertEqual(_names(), ["Raider 1", "Raider 2"])
        self.assertIn("figure_ambiguous", [c.args[1] for c in note.call_args_list])

    def test_the_count_is_per_kind_across_the_save(self):
        from app import db

        _play("A rotting ghoul lunges at you from the shadows.", "i look around", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        with db.connect().closing() as conn:
            other = conn.execute("SELECT id FROM locations WHERE id != (SELECT current_location_id FROM player) LIMIT 1").fetchone()
            if other is None:
                conn.execute("INSERT INTO locations (code, name, summary) VALUES ('L99', 'Old Tunnel', 'A tunnel.')")
                other = conn.execute("SELECT id FROM locations WHERE code = 'L99'").fetchone()
            conn.execute("UPDATE npcs SET location_id = ? WHERE kind = 'Ghoul'", (int(other[0]),))
            conn.commit()
        _play("A ghoul lunges at you from a broken window.", "i shoot", _Asker(hostile=("ghoul",)))
        self.assertEqual(_names(), ["Ghoul 1", "Ghoul 2"])

    def test_an_unnamed_guard_in_a_town(self):
        _play("A guard in a dented helmet steps in front of you.", "i walk to the gate", _Asker())
        rows = _rows()
        self.assertEqual([(r["name"], r["kind"], r["kind_number"]) for r in rows], [("Guard 1", "Guard", 1)])
        self.assertIn("guard", rows[0]["role"].lower())
        self.assertNotEqual(rows[0]["race"], "unknown")

    def test_t3_the_nurse_is_one_numbered_row(self):
        # cc87dd29 T3 as shipped: the line nobody known speaks seeded a face
        # under a drawn name ("Beth"). That face is the nurse: numbered, not a
        # second row beside it.
        _play(T3_PROSE, "I go into the clinic.", _Asker(figures=("nurse",)))
        here = _rows("id > 0 AND location_id = (SELECT current_location_id FROM player)")
        nurses = [r for r in here if r["kind"] == "Nurse"]
        self.assertEqual([r["name"] for r in nurses], ["Nurse 1"])
        self.assertEqual([r for r in here if r["kind"] == "" and r["name"] not in T3_PROSE], [])

    def test_a_crowd_is_not_numbered(self):
        # Baseline replay T0: "A few people move between the open fronts of shops".
        _play(BASELINE_T0, "(opening)", _Asker())
        self.assertEqual(_names(), [])

    def test_a_named_person_is_not_numbered(self):
        _play("A raider named Kade levels his rifle at you.", "i stop", _Asker(figures=("raider",), hostile=("raider",)))
        self.assertEqual(_names(), [])
        self.assertIn("Kade", _names("1 = 1"))

    def test_named_later_keeps_the_code(self):
        _play("A raider steps out from behind the wreck and levels a rifle at you.", "i stop",
              _Asker(figures=("raider",), hostile=("raider",)))
        before = _rows()
        self.assertEqual([r["name"] for r in before], ["Raider 1"])
        _play("The raider, who says his name is Kade, lowers his rifle.", "who are you?", _Asker())
        after = _rows()
        self.assertEqual([(r["code"], r["name"], r["kind_number"]) for r in after], [(before[0]["code"], "Kade", 1)])
        self.assertNotIn("Kade", [r["name"] for r in _rows("kind = ''")])
        # The next raider is the second ever met.
        _play("Another raider steps out and aims at you.", "i duck", _Asker(hostile=("raider",)))
        self.assertEqual(_names(), ["Kade", "Raider 2"])

    def test_an_op_that_introduces_a_kind(self):
        asker = _Asker(entity_kind="place")
        _play("A ghoul lunges at you from the dark. The ghoul hisses.", "i look",
              asker, ops='SUMMARY: "A ghoul attacks."\nNPC_NEW NAME "Ghoul" ROLE "monster" ATTITUDE hostile')
        rows = _rows()
        self.assertEqual([(r["name"], r["attitude"]) for r in rows], [("Ghoul 1", "hostile")])
        self.assertNotIn("Ghoul", _names("1 = 1"))
        # Not asked person-or-place (a creature was answered "place"), nor hostile (the op said).
        self.assertFalse(any('"Ghoul"' in u for u in asker.asked("entity_kind")))
        self.assertEqual(asker.asked("figure_hostile"), [])

    def test_rewind_removes_the_rows_and_the_name(self):
        from app import world

        _play("A raider steps out from behind the wreck and levels a rifle at you.", "i stop",
              _Asker(figures=("raider",), hostile=("raider",)))
        code = _rows()[0]["code"]
        _play("The raider, who says his name is Kade, lowers his rifle.", "who are you?", _Asker())
        self.assertEqual(_names(), ["Kade"])
        world.rewind_last_turn()
        self.assertEqual([(r["code"], r["name"]) for r in _rows()], [(code, "Raider 1")])
        world.rewind_last_turn()
        self.assertEqual(_names(), [])
        _play(GHOULS_PROSE, GHOULS_LINE, _Asker(figures=("ghoul",), hostile=("ghoul",)))
        world.rewind_last_turn()
        self.assertEqual(_names(), [])
        _play("A rotting ghoul lunges at you from the shadows.", "i look", _Asker(figures=("ghoul",)))
        self.assertEqual(_names(), ["Ghoul 1"])


class AttackOnTheGhoul(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_i_shoot_the_ghoul_rolls_on_ghoul_1(self):
        from app import attack_intent, world

        _play("A rotting ghoul lunges at you from the shadows.", "i look around", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        ghoul = _rows()[0]
        context = world.get_state(include_hidden=True)
        from app.conversation import resolve

        context["conversation_turn"] = resolve(context, "i shoot the ghoul")
        prompts: list[str] = []

        def ask(phase, prompt, max_tokens):
            prompts.append(prompt)
            if phase == attack_intent.PHASE_ATTACK:
                return "Yes" if "kill the ghoul?" in prompt else "No"
            return "No"

        check, report = attack_intent.decide("i shoot the ghoul", context, None, ask)
        self.assertIsNotNone(check, report)
        self.assertEqual(check["attack"]["code"], ghoul["code"])
        self.assertEqual(check["opposition"]["attitude"], "hostile")
        self.assertTrue(prompts[0].startswith("The ghoul is here."), prompts[0])

    def test_a_named_person_is_still_asked_by_name(self):
        from app.unnamed import ask_label

        self.assertEqual(ask_label({"name": "Beth"}, [{"name": "Beth"}]), "Beth")
        two = [{"name": "Ghoul 1", "kind": "Ghoul", "kind_number": 1}, {"name": "Ghoul 2", "kind": "Ghoul", "kind_number": 2}]
        self.assertEqual(ask_label(two[0], two), "Ghoul 1")
        self.assertEqual(ask_label(two[0], two[:1]), "the ghoul")
        self.assertEqual(ask_label({"name": "Kade", "kind": "Raider", "kind_number": 1}, []), "Kade")


class OldSaves(unittest.TestCase):
    def test_a_save_without_the_columns_gets_them(self):
        from app import db

        _fresh_world()
        with db.connect().closing() as conn:
            conn.execute("ALTER TABLE npcs DROP COLUMN kind_number")
            conn.execute("ALTER TABLE npcs DROP COLUMN kind")
            conn.commit()
        db.init_db()
        with db.connect().closing() as conn:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(npcs)").fetchall()}
        self.assertTrue({"kind", "kind_number"} <= columns)


if __name__ == "__main__":
    unittest.main()
