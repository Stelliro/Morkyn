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
    """The model, scripted: both figure checks yes for the nouns given (the second check only for
    ``checked``, when given), figure_hostile per noun; every call kept. The replies are the ones
    Hermes 3 8B gave to these asks (live-eval-5): cut at 4 tokens, never a bare word."""

    def __init__(self, figures=(), hostile=(), entity_kind="person", checked=None, speaks=None):
        self.figures = {f.lower() for f in figures}
        # figure_speaks (live-eval-6): Hermes answers this wording with a plain "Yes" / "No.".
        self.speaks = self.figures if speaks is None else {s.lower() for s in speaks}
        self.checked = self.figures if checked is None else {c.lower() for c in checked}
        self.hostile = {h.lower() for h in hostile}
        self.entity_kind = entity_kind
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system, user, *, trace=None, usage=None, phase="", max_tokens=None):
        self.calls.append((phase, user))
        if phase == "figure_kind":
            return "Yes, in this" if any(f'is "{f}" a being' in user for f in self.figures) else "No, in this"
        if phase == "figure_kind_check":
            return "Yes." if any(f"is the {f} a creature or a person?" in user for f in self.checked) else "No."
        if phase == "figure_speaks":
            return "Yes." if any(f"spoken by the {s}?" in user for s in self.speaks) else "No."
        if phase == "figure_hostile":
            return 'Yes, "a' if any(h in user.lower() for h in self.hostile) else 'No, "a'
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
        self.assertIn('is "deathclaw" a being that can act on its own?', asker.asked("figure_kind")[0])

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


# Recorded narration sentences (cc87dd29, live/integ-r3, live/final) the
# branch's first reader put to the figure ask: scenery, every one.
SCENERY_OBJECTS = (
    "The radiation sensors on your X-01 power armor flash a warning - supplies are running low, and the thought of "
    "facing these mutated scavengers sends a chill down your spine.",
    "An ironbound door is your only way in, and it is sealed shut.",
    "As you stand over the two halves of the dismembered doctor, you hear a scream from inside the clinic.",
    "You see a few scattered buildings in the distance but nothing close.",
)
SCENERY_SUBJECTS = (
    "A counter separates you from the room's only other occupant, a woman with graying hair and a stern expression.",
    "A sickening tear rips through her flesh as you wrench her body apart.",
    "You bellow a chilling war cry as you storm into the clinic, a grim look of fury etched upon your armored visor.",
)


class TheFigureGate(unittest.TestCase):
    """A noun is asked about only when the figure does something; two asks must agree before it is filed."""

    def setUp(self):
        _fresh_world()

    def test_an_object_or_a_noun_in_a_phrase_is_never_asked(self):
        # Yes to every noun that is no figure: an object of something else's verb, a noun after
        # "is", the head of a prepositional phrase. Only what the player sees or hears is asked
        # (the scream, the buildings), and the pair answers those no: nothing is filed.
        for prose in SCENERY_OBJECTS:
            asker = _Asker(figures=("warning", "door", "half"))
            _play(prose, "i look around", asker)
            asked = [u.split('is "')[1].split('"')[0] for u in asker.asked("figure_kind")]
            self.assertEqual([n for n in asked if n not in {"scream", "building"}], [], prose)
        self.assertEqual(_names(), [])

    def test_the_structure_reads_the_subject(self):
        from app import unnamed

        def kinds(text, objects=()):
            return [(m["kind"], m["subject"], m["acts"]) for m in unnamed.mentions(text, objects)]

        # "a flicker of understanding" is a flicker, not a group of "passes".
        self.assertEqual(kinds("A flicker of understanding passes between you."), [("flicker", True, True)])
        self.assertEqual(kinds("You see 4 ghouls eating someone."), [("ghoul", True, True)])
        self.assertEqual(kinds("From behind the counter a ghoul lunges at you."), [("ghoul", True, True)])
        self.assertEqual(kinds("A raider is aiming at you."), [("raider", True, True)])
        self.assertEqual(kinds("A raider is here."), [("raider", True, False)])
        self.assertEqual(kinds("You shoot at a ghoul in the doorway."), [])
        self.assertEqual(kinds("You shoot at a ghoul in the doorway.", {"ghoul"}), [("ghoul", False, True)])

    def test_one_yes_files_nothing(self):
        # A yes-leaning first ask: the second, differently worded one says no.
        for prose in SCENERY_SUBJECTS + (T2_PROSE,):
            asker = _Asker(figures=("counter", "tear", "look", "ping", "cry"), checked=())
            _play(prose, "i look around", asker)
            self.assertEqual(len(asker.asked("figure_kind_check")), len(asker.asked("figure_kind")), prose)
            self.assertTrue(asker.asked("figure_kind"), prose)
        # The woman behind the counter is a figure the hints know (Woman 1); no scenery is.
        self.assertEqual([n for n in _names() if not n.startswith("Woman ")], [])
        self.assertEqual(_names("kind IN ('Ping', 'Counter', 'Tear', 'Look', 'Cry')"), [])

    def test_both_asks_yes_files_the_figure(self):
        asker = _Asker(figures=("ghoul",), hostile=("ghoul",))
        _play("A rotting ghoul lunges at you from the shadows.", "i look around", asker)
        self.assertEqual(_names(), ["Ghoul 1"])
        self.assertEqual(asker.asked("figure_kind_check"),
                         ["Text: A rotting ghoul lunges at you from the shadows.\n"
                          "In this text, is the ghoul a creature or a person? Answer yes or no."])
        # Only the first said yes: no ghoul.
        _fresh_world()
        _play("A rotting ghoul lunges at you from the shadows.", "i look around", _Asker(figures=("ghoul",), checked=()))
        self.assertEqual(_names(), [])
        # The second is not asked after a no.
        asker = _Asker(figures=())
        _play("A rotting ghoul lunges at you from the shadows.", "i look around", asker)
        self.assertEqual(asker.asked("figure_kind_check"), [])

    def test_the_players_own_act_makes_its_object_a_candidate(self):
        from app import unnamed

        self.assertEqual(unnamed.player_objects("i shoot the ghoul"), {"ghoul"})
        self.assertEqual(unnamed.player_objects("I duck and attack the nearest raider with my knife"), {"raider"})
        self.assertEqual(unnamed.player_objects("I go into the clinic"), set())
        self.assertEqual(unnamed.player_objects('i say "shoot the ghoul"'), set())
        prose = "Your shot takes a ghoul in the shoulder and it reels."
        _play(prose, "i look around", _Asker(figures=("ghoul",)))
        self.assertEqual(_names(), [])
        _play(prose, "i shoot the ghoul", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        self.assertEqual(_names(), ["Ghoul 1"])


class TwoFiguresInOneTurn(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_a_shouted_warning_and_a_ghoul_are_two_figures(self):
        prose = '"Get down!" someone shouts from behind the counter. A ghoul lunges at you from the doorway.'
        _play(prose, "i duck", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        here = _rows("location_id = (SELECT current_location_id FROM player)")
        ghouls = [r for r in here if r["kind"] == "Ghoul"]
        self.assertEqual([(r["name"], r["attitude"], r["race"]) for r in ghouls], [("Ghoul 1", "hostile", "unknown")])
        speakers = [r for r in here if r["kind"] == ""]
        self.assertEqual(len(speakers), 1, here)
        self.assertNotEqual(speakers[0]["attitude"], "hostile")

    def test_who_speaks_each_line(self):
        from app import unnamed

        # "she asks" after the nurse: hers only when the figure_speaks ask said so (no person word).
        self.assertEqual(unnamed.speaker_kinds(T3_PROSE), [""])
        self.assertEqual(unnamed.speaker_kinds(T3_PROSE, ["nurse"]), ["nurse"])
        self.assertEqual(unnamed.speaker_kinds('A guard steps out. "Halt!" he says.'), ["guard"])
        self.assertEqual(unnamed.speaker_kinds('"Get down!" someone shouts. A ghoul lunges at you.'), ["someone"])
        self.assertEqual(unnamed.speaker_kinds('A guard steps out. "Halt," says the guard.'), ["guard"])


class TheyDoNotVanish(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_a_ghoul_the_prose_keeps_showing_stays(self):
        # The skeptic's replay: Ghoul 1 faded at turn 6 while every turn said "The ghoul circles you".
        _play("A rotting ghoul lunges at you from the shadows.", "i look", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        for _ in range(8):
            _play("The ghoul circles you, snarling.", "i wait", _Asker())
        self.assertEqual(_names(), ["Ghoul 1"])

    def test_several_ghouls_in_a_fight_stay(self):
        _play(GHOULS_PROSE, GHOULS_LINE, _Asker(figures=("ghoul",), hostile=("ghoul",)))
        for _ in range(8):
            _play("The ghouls press in around you, snapping.", "i swing my rifle at them", _Asker())
        self.assertEqual(_names(), ["Ghoul 1", "Ghoul 2", "Ghoul 3", "Ghoul 4"])


class EachGameCountsItsOwn(unittest.TestCase):
    def test_a_new_game_starts_at_ghoul_1(self):
        from app import db, sketches, world

        _fresh_world()
        _play("A rotting ghoul lunges at you from the shadows.", "i look", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        with db.connect().closing() as conn:
            row = conn.execute("SELECT * FROM npcs WHERE kind = 'Ghoul'").fetchone()
            sketches._fade(conn, row, 9, {"faded": []})
            conn.commit()
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM faded_people").fetchone()[0], 1)
        _play("A ghoul lunges at you from a broken window.", "i look", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        self.assertEqual(_names(), ["Ghoul 2"])  # the faded one still counts in its own game
        world.start_playthrough({"player_name": "Ann Other", "start_location": "Radiation Fenced Sanctuary",
                                 "special_ability_origin": "none"})
        with db.connect().closing() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM faded_people").fetchone()[0], 0)
        _play("A rotting ghoul lunges at you from the shadows.", "i look", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        self.assertEqual(_names(), ["Ghoul 1"])


class TheStorySeesWhatTheyAre(unittest.TestCase):
    """The record and the UI number them; the narrator's packet shows what they are, with the code."""

    def setUp(self):
        _fresh_world()

    def test_the_packet_shows_an_unnamed_ghoul(self):
        from app import prompts, world

        _play("A rotting ghoul lunges at you from the shadows.", "i look around", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        _play("A guard in a dented helmet steps in front of you.", "i wait", _Asker())
        rows = {r["kind"]: r for r in _rows()}
        self.assertEqual({rows["Ghoul"]["name"], rows["Guard"]["name"]}, {"Ghoul 1", "Guard 1"})
        state = world.get_state(include_hidden=True)
        self.assertIn("Ghoul 1", json.dumps(state))  # the save and the UI keep the number
        context = world.build_prompt_context(state, "i shoot the ghoul")
        packet = prompts.build_user_prompt(context, "i shoot the ghoul")
        self.assertNotIn("Ghoul 1", packet)
        self.assertNotIn("Guard 1", packet)
        people = json.loads(packet)["world_state"]["current_location"].get("people") or []
        shown = {p["code"]: p["name"] for p in people}
        self.assertEqual(shown.get(rows["Ghoul"]["code"]), "an unnamed ghoul")
        self.assertEqual(shown.get(rows["Guard"]["code"]), "an unnamed guard")

    def test_a_figure_named_later_is_shown_by_name(self):
        from app import unnamed

        records = {"locations": [{"npcs": [
            {"name": "Kade", "kind": "Raider", "kind_number": 1, "code": "A"},
            {"name": "Ghoul 1", "kind": "Ghoul", "kind_number": 1, "code": "B"},
            {"name": "Ghoul 10", "kind": "Ghoul", "kind_number": 10, "code": "C"},
        ]}]}
        names = unnamed.story_names(records)
        self.assertEqual(names, {"Ghoul 1": "an unnamed ghoul", "Ghoul 10": "an unnamed ghoul"})
        view = unnamed.story_view({"line": "Ghoul 1 [[B]] and Ghoul 10 [[C]] circle Kade [[A]]."}, names)
        self.assertEqual(view["line"], "an unnamed ghoul [[B]] and an unnamed ghoul [[C]] circle Kade [[A]].")
        self.assertEqual(unnamed.story_label("Woman"), "an unnamed woman")
        self.assertEqual(unnamed.story_label("Raider"), "an unnamed raider")

    def test_the_paragraph_briefs_show_it_too(self):
        from app import narration_pipeline, unnamed

        context = {"current_location": {"name": "Clinic", "code": "L1", "npcs": [
            {"name": "Woman 1", "kind": "Woman", "kind_number": 1, "code": "B", "role": "local"}]}}
        captured = {}
        real = unnamed.story_view

        def spy(value, names):
            captured["names"] = names
            return real(value, names)

        from unittest import mock

        with mock.patch.object(unnamed, "story_view", side_effect=spy):
            briefs = narration_pipeline.build_paragraph_briefs(
                {"paragraphs": 1}, context, "i talk to Woman 1",
                narration_pipeline.NarrationLedger(1, "i talk to Woman 1", {"paragraphs": 1}))
        self.assertEqual(captured["names"], {"Woman 1": "an unnamed woman"})
        self.assertNotIn("Woman 1", json.dumps(briefs))


class TheMeasuredAsks(unittest.TestCase):
    """The asks as live-eval-5 measured them on Hermes 3 8B (scratchpad live-eval-5/results.json)."""

    def test_the_kind_and_check_asks_are_the_measured_wording(self):
        from app import unnamed

        self.assertEqual(unnamed.kind_prompt("A ghoul lunges at you.", "ghoul"),
                         'Text: A ghoul lunges at you.\nIn this text, is "ghoul" a being that can act on its own?')
        self.assertEqual(unnamed.kind_check_prompt("A ghoul lunges at you.", "ghoul"),
                         "Text: A ghoul lunges at you.\n"
                         "In this text, is the ghoul a creature or a person? Answer yes or no.")
        self.assertEqual(unnamed.hostile_prompt("A ghoul lunges at you.", "A ghoul"),
                         'Text: A ghoul lunges at you.\nIn this text, does "A ghoul" attack or threaten the player?')

    def test_the_measured_replies_are_read(self):
        from app.entity_kinds import read_yes_no

        # The replies the 8B gave, cut at 4 tokens.
        for reply in ("Yes, in this", 'Yes, "gh', "Yes, a Death", "Yes, you could", 'Yes, "a'):
            self.assertIs(read_yes_no(reply), True, reply)
        for reply in ("No, in this", 'No, "ping', "No.", "No. The flick", 'No, "a'):
            self.assertIs(read_yes_no(reply), False, reply)


class NoNumberInTheStory(unittest.TestCase):
    """The numbered label is the save's and the UI's; the narrator and the prose see what the figure is."""

    def setUp(self):
        _fresh_world()

    def test_prose_view(self):
        from app import unnamed

        names = {"Ghoul 1": "the ghoul", "Ghoul 2": "the ghoul", "Guard 1": "the guard"}
        self.assertEqual(unnamed.prose_view("The ghoul [[A]] snarls while Ghoul 2 [[B]] lunges at you.", names),
                         "The ghoul [[A]] snarls while the ghoul [[B]] lunges at you.")
        self.assertEqual(unnamed.prose_view("Ghoul 2 [[B]] lunges. \"Down!\" Guard 1 shouts.", names),
                         "The ghoul [[B]] lunges. \"Down!\" The guard shouts.")
        self.assertEqual(unnamed.prose_view("You hit the Ghoul 1 [[A]].", names), "You hit the ghoul [[A]].")
        # Ghoul 10 is not Ghoul 1; a name told later is not numbered.
        self.assertEqual(unnamed.prose_view("Ghoul 10 and Kade wait.", names), "Ghoul 10 and Kade wait.")
        self.assertEqual(unnamed.story_label("Ghoul", definite=True), "the ghoul")

    def _turn(self, narrator_prose):
        """One real play_turn with every model call recorded (the transport mocked)."""
        from unittest import mock

        from app import llm, world

        rows = {r["name"]: r["code"] for r in _rows()}
        sent: list[tuple[str, str]] = []
        draft = "===NAR===\n" + narrator_prose.format(**{k.replace(" ", ""): v for k, v in rows.items()}) + \
            '\n\n===OPS===\nSUMMARY: "Ghouls circle."\n'

        def fake(system_prompt, user_prompt, *args, **kwargs):
            sent.append((system_prompt, user_prompt))
            if "===NAR===" in (system_prompt + user_prompt) or "nar_ops" in user_prompt:
                return draft
            return "no"

        with mock.patch.object(llm, "_chat_content", side_effect=fake):
            out = world.play_turn("i shoot the ghoul")
        turn = (out or {}).get("turn") or {}
        return sent, str(turn.get("narration") or "") if isinstance(turn, dict) else ""

    def test_the_whole_packet_and_the_prose_carry_no_number(self):
        import re

        _play("A ghoul lunges at you from the shadows.", "i look around", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        _play("A guard in a dented helmet steps in front of you.", "i wait", _Asker())
        self.assertEqual(sorted(r["name"] for r in _rows()), ["Ghoul 1", "Guard 1"])
        # The 8B leaves a bare person code now and then (2 of 43 recorded outputs): the repair fills it.
        sent, narration = self._turn("The ghoul circles you while [[{Ghoul1}]] snarls. [[{Guard1}]] raises his baton.")
        label = re.compile(r"\b(?:Ghoul|Guard) \d+\b")
        self.assertGreater(len(sent), 3)
        for system, user in sent:
            self.assertEqual(label.findall(system + "\n" + user), [], user[:160])
        self.assertTrue(narration)
        self.assertEqual(label.findall(narration), [], narration)
        self.assertIn("the ghoul [[", narration)
        self.assertIn("The guard [[", narration)

    def test_two_of_a_kind_still_reach_the_narrator_as_what_they_are(self):
        import re

        _play("Two ghouls lunge at you from the shadows.", "i look around", _Asker(figures=("ghoul",), hostile=("ghoul",)))
        _play("A guard in a dented helmet steps in front of you.", "i wait", _Asker())
        sent, narration = self._turn("The ghoul [[{Ghoul1}]] snarls and circles you while [[{Ghoul2}]] lunges at you.")
        label = re.compile(r"\b(?:Ghoul|Guard) \d+\b")
        # What the narrator is sent (the scene packet, the rewrite, the repair) and what the player reads.
        story = [u for _s, u in sent if '"world_state"' in u or "Rewrite this scene" in u or "repair_task" in u]
        self.assertTrue(story)
        for user in story:
            self.assertEqual(label.findall(user), [], user[:160])
        self.assertIn("an unnamed ghoul [[", "\n".join(story))
        self.assertEqual(label.findall(narration), [], narration)
        # A small ask about plain text keeps the number only where two would read alike ("Is Ghoul 1 dead").
        for _s, user in sent:
            if "Read this." in user:
                self.assertEqual([n for n in label.findall(user) if n.startswith("Guard")], [], user)

    def test_the_engine_lines_written_into_the_prose(self):
        from app import interpreter

        row = {"code": "B", "name": "Ghoul 2", "kind": "Ghoul", "kind_number": 2, "location_id": 3}
        self.assertEqual(interpreter.outcome_beat(row, None), "The ghoul [[B]] is still alive.")
        means = interpreter.dead_talk_outcome(row, "i talk to the ghoul", here=True)
        self.assertNotIn("Ghoul 2", json.dumps(means))
        twin = {**row, "code": "A", "name": "Ghoul 1", "kind_number": 1}
        self.assertEqual(interpreter.called(row, [row]), "the ghoul")
        self.assertEqual(interpreter.called(row, [row, twin]), "Ghoul 2")
        self.assertEqual(interpreter.called(row, [row, twin], prose=True), "the ghoul")
        self.assertEqual(interpreter.called({"code": "C", "name": "Kade", "kind": "Raider", "kind_number": 1}), "Kade")
        # The turn summary the next turn's narrator reads.
        died = interpreter._event(interpreter.KIND_DIED, "npc", row, "The ghoul falls still.")
        self.assertEqual(died["subject"]["name"], "Ghoul 2")
        self.assertEqual(interpreter.event_line(died), "The ghoul [[B]] died.")
        carried = {**died, "kind": interpreter.KIND_BODY, "state": interpreter.BODY_CARRIED}
        self.assertEqual(interpreter.event_line(carried), "You carry the body of the ghoul [[B]].")
        beth = interpreter._event(interpreter.KIND_DIED, "npc", {"code": "A", "name": "Beth"}, "Beth falls.")
        self.assertNotIn("story", beth["subject"])

    def test_a_save_without_the_kind_columns_still_loads_its_records(self):
        import sqlite3

        from app import interpreter

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE npcs (code TEXT, name TEXT, died_turn INTEGER, location_id INTEGER, body TEXT)")
        conn.execute("INSERT INTO npcs VALUES ('A', 'Beth', 0, 1, '')")
        people = interpreter.load_records(conn)["people"]
        conn.close()
        self.assertEqual([(p["name"], p["kind"], p["kind_number"]) for p in people], [("Beth", "", 0)])


class NeverAcrossKinds(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_same_kind(self):
        from app import sketches

        ghoul = {"kind": "Ghoul", "kind_number": 1, "role": "ghoul"}
        guard = {"kind": "Guard", "kind_number": 1, "role": "guard"}
        aldric = {"kind": "", "kind_number": 0, "role": "gate guard"}
        beth = {"kind": "", "kind_number": 0, "role": "trader"}
        woman = {"kind": "Woman", "kind_number": 1, "role": "woman"}
        self.assertFalse(sketches.same_kind(ghoul, guard))
        self.assertTrue(sketches.same_kind(guard, aldric))
        self.assertFalse(sketches.same_kind(ghoul, beth))
        self.assertFalse(sketches.same_kind(woman, ghoul))
        # A vague person word is anyone, as before the numbering.
        self.assertTrue(sketches.same_kind(woman, beth))
        self.assertTrue(sketches.same_kind(beth, aldric))

    def test_a_wrong_identity_answer_does_not_merge_a_ghoul_into_a_guard(self):
        import re

        from app import sketches

        asked: list[str] = []

        def first_code(system, user, **kw):
            asked.append(user)
            codes = re.findall(r"^([A-Z]{1,2}): ", user, re.M)
            return '{"answer": "%s"}' % codes[0] if codes else '{"answer": "new"}'

        previous = sketches.set_identity_ask(first_code)
        try:
            _play("A ghoul lunges at you from the shadows. A guard in a dented helmet steps in front of you.", "i look",
                  _Asker(figures=("ghoul",), hostile=("ghoul",)))
            for prose in ("The ghoul circles you, snarling. The guard watches you, baton raised.",
                          "The ghoul circles you, snarling."):
                _play(prose, "i wait", _Asker())
        finally:
            sketches.set_identity_ask(previous)
        rows = {r["name"]: (r["attitude"], r["role"]) for r in _rows()}
        self.assertEqual(rows, {"Ghoul 1": ("hostile", "ghoul"), "Guard 1": ("neutral", "guard")})
        for user in asked:
            self.assertFalse("Ghoul 1" in user and "Guard 1" in user, user)


class ThePronounInASpeechTag(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_she_after_a_ghoul_is_not_the_ghoul(self):
        prose = 'A ghoul lunges at you from the doorway. "Get down!" she shouts from behind the counter.'
        asker = _Asker(figures=("ghoul",), hostile=("ghoul",), speaks=())
        _play(prose, "i duck", asker)
        here = _rows("location_id = (SELECT current_location_id FROM player)")
        ghouls = [r for r in here if r["kind"] == "Ghoul"]
        self.assertEqual([(r["name"], r["attitude"], r["race"]) for r in ghouls], [("Ghoul 1", "hostile", "unknown")])
        speakers = [r for r in here if r["kind"] == ""]
        self.assertEqual(len(speakers), 1, [dict(r) for r in here])
        self.assertNotEqual(speakers[0]["attitude"], "hostile")
        self.assertEqual(asker.asked("figure_speaks"),
                         ['Text: A ghoul lunges at you from the doorway. "Get down!" she shouts from behind the counter.\n'
                          'In this text, are the words "Get down!" spoken by the ghoul? Answer yes or no.'])

    def test_offline_the_face_stays_the_speaker(self):
        from app import entity_kinds, world
        from app.turn_dsl import parse_dsl_turn

        prose = 'A ghoul lunges at you from the doorway. "Get down!" she shouts from behind the counter.'
        turn = parse_dsl_turn(f'===NAR===\n{prose}\n\n===OPS===\nSUMMARY: "A ghoul."\nNPC_NEW NAME "Ghoul" ROLE "monster" '
                              'ATTITUDE hostile\n', "i duck")
        turn["narration"] = prose
        entity_kinds.settle_kinds(turn, "i duck", ask=False)
        world.apply_turn(turn, "i duck", input_kind="player")
        here = _rows("location_id = (SELECT current_location_id FROM player)")
        self.assertEqual([r["name"] for r in here if r["kind"] == "Ghoul"], ["Ghoul 1"])
        self.assertEqual(len([r for r in here if r["kind"] == ""]), 1, [dict(r) for r in here])


class TheDeadKeepTheirStoryName(unittest.TestCase):
    """The second reviewer: after a numbered figure died, its body and death facts carried "Ghoul 1" to the narrator."""

    def test_a_dead_ghoul_is_the_ghoul_in_the_facts_and_bodies(self):
        from app import interpreter as I
        from app.unnamed import story_names, story_view

        state = {"current_location": {"id": 2, "code": "L2"}, "locations": [{"id": 2, "code": "L2", "npcs": [
            {"code": "A", "name": "Ghoul 1", "kind": "Ghoul", "kind_number": 1, "died_turn": 3, "location_id": 2}]}]}
        context = {"current_location": {"id": 2, "code": "L2", "npcs": []}, "locations": [{"id": 2, "code": "L2", "npcs": []}]}
        I.hold_context(state, context)
        facts = I.facts(context)
        self.assertTrue(facts, context)
        self.assertFalse(any("Ghoul 1" in f for f in facts), facts)
        self.assertEqual(facts[0], "The ghoul [[A]] dead=1")  # #154: the 0/1 flag, story label
        self.assertIn("The body of the ghoul [[A]] lies here.", facts)
        names = story_names(context)
        self.assertIn("Ghoul 1", names)
        viewed = story_view(context, names)
        self.assertNotIn("Ghoul 1", repr(viewed))

    def test_a_named_dead_person_keeps_the_name(self):
        from app import interpreter as I

        state = {"current_location": {"id": 2, "code": "L2"}, "locations": [{"id": 2, "code": "L2", "npcs": [
            {"code": "B", "name": "Beth", "died_turn": 10, "location_id": 2}]}]}
        context = {"current_location": {"id": 2, "code": "L2", "npcs": []}, "locations": [{"id": 2, "code": "L2", "npcs": []}]}
        I.hold_context(state, context)
        self.assertEqual(I.facts(context)[0], "Beth [[B]] dead=1")


class ACreatureThatSpeaksIsTheCreature(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_raider_takes_no_drawn_role_or_race(self):
        # The reviewer's probe (verifyU2-scratch/speak.py).
        prose = 'A raider steps out and levels a rifle at you. "Drop it," he growls.'
        asker = _Asker(figures=("raider",), hostile=("raider",), speaks=("raider",))
        _play(prose, "i freeze", asker)
        raiders = [r for r in _rows() if r["kind"] == "Raider"]
        self.assertEqual(len(raiders), 1, [dict(r) for r in _rows("1=1")])
        self.assertNotEqual(raiders[0]["role"], "scribe")


class MoreAndReferredBack(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_two_more_ghouls_are_two_more(self):
        _play("A ghoul lunges at you from the shadows. Then two more ghouls follow.", "i back away",
              _Asker(figures=("ghoul",), hostile=("ghoul",)))
        self.assertEqual(_names(), ["Ghoul 1", "Ghoul 2", "Ghoul 3"])
        _play("One more ghoul drops from the roof onto you.", "i fight", _Asker())
        self.assertEqual(_names(), ["Ghoul 1", "Ghoul 2", "Ghoul 3", "Ghoul 4"])

    def test_a_deathclaw_referred_back_to_mints_nothing_without_an_op(self):
        asker = _Asker(figures=("deathclaw",), hostile=("deathclaw",))
        _play("The deathclaw charges you, roaring.", "i brace", asker)
        self.assertEqual(_names(), [])
        self.assertEqual(asker.asked("figure_kind"), [])
        _play("The deathclaw charges you, roaring.", "i brace", asker,
              ops='SUMMARY: "A deathclaw charges."\nNPC_NEW NAME "Deathclaw" ROLE "monster" ATTITUDE hostile')
        self.assertEqual(_names(), ["Deathclaw 1"])


# Live run unnamed2 T1 on Hermes 3 8B (turns/001.json), verbatim: the ghouls are what the player sees.
UNNAMED2_T1_LINE = "I creep into the ruined subway tunnel where a pack of ghouls is feeding on a carcass"
UNNAMED2_T1_PROSE = (
    "Morning mist drifts across the cracked asphalt of the old highway as you creep into the ruined subway tunnel "
    "entrance. The rusted metal door hangs partway off its hinges. Through the gap, you see a pack of ghouls feasting "
    "on a bloated corpse. Their milky eyes stare in your direction as you move silently in your X-01 power armor "
    "[[I2]]. They are not hungry enough to abandon their meal to attack you.\n\nAs you slip past, a faint voice calls "
    "out from deeper in the shadows, \"You're going the wrong way. The other tunnel leads to the old power plant. It's "
    "got salvageable tech inside, if you know how to use it.\"\n\nCarlos Khan [[A]] steps into the pale morning light, "
    "his ranger's bow in hand. He is not a friend."
)


class _RecordedAsker(_Asker):
    """The replies Hermes 3 8B gave (live-eval-5 and the unnamed2 trace), keyed by the exact prompt.

    unnamed2 T1's own figure_kind reply was 'Yes, "gh'. Its check, with the wording measured in
    live-eval-7 ("is the ghoul a creature or a person?"), answered 'Yes, a gh' on this exact
    sentence (the old "could you fight or talk to" answered "No."). figure_hostile was never asked live on
    this sentence; the reply is the one measured on "You see 4 ghouls eating someone" (3 of 3).
    """

    REPLIES = {
        ("figure_kind", "Through the gap, you see a pack of ghouls feasting on a bloated corpse.", "ghoul"): 'Yes, "gh',
        ("figure_kind_check", "Through the gap, you see a pack of ghouls feasting on a bloated corpse.", "ghoul"):
            "Yes, a gh",
        ("figure_hostile", "Through the gap, you see a pack of ghouls feasting on a bloated corpse.", "ghoul"):
            "No, the text",
    }

    def __call__(self, system, user, *, trace=None, usage=None, phase="", max_tokens=None):
        sentence = user.split("\n")[0][len("Text: "):]
        for (p, s, noun), reply in self.REPLIES.items():
            if p == phase and s == sentence and noun in user.split("\n")[-1]:
                self.calls.append((phase, user))
                return reply
        return super().__call__(system, user, trace=trace, usage=usage, phase=phase, max_tokens=max_tokens)


class WhatThePlayerSees(unittest.TestCase):
    """A figure the prose shows present is asked about: the object of the player's seeing, an -ing
    or a relative clause after it, not only the subject of a verb (unnamed2 T1)."""

    def setUp(self):
        _fresh_world()

    def test_unnamed2_t1_mints_two_ghouls(self):
        asker = _RecordedAsker()
        _play(UNNAMED2_T1_PROSE, UNNAMED2_T1_LINE, asker)
        rows = _rows()
        self.assertEqual([r["name"] for r in rows], ["Ghoul 1", "Ghoul 2"])
        # figure_hostile said no: feasting on a corpse is no threat to the player.
        self.assertEqual([r["attitude"] for r in rows if r["attitude"] == "hostile"], [])
        self.assertEqual(asker.asked("figure_kind"),
                         ['Text: Through the gap, you see a pack of ghouls feasting on a bloated corpse.\n'
                          'In this text, is "ghoul" a being that can act on its own?'])
        # The group was not counted: two now; later prose that counts more adds the rest.
        _play("Another ghoul drops from the ceiling behind you.", "i back away", _Asker(hostile=("ghoul",)))
        self.assertEqual(_names(), ["Ghoul 1", "Ghoul 2", "Ghoul 3"])
        _play("Some ghouls shamble toward you.", "i back away", _Asker())
        self.assertEqual(_names(), ["Ghoul 1", "Ghoul 2", "Ghoul 3"])

    def test_the_third_ghoul_after_an_uncounted_pack(self):
        _play("You see a pack of ghouls.", "i look", _Asker(figures=("ghoul",)))
        self.assertEqual(_names(), ["Ghoul 1", "Ghoul 2"])
        _play("The third ghoul lunges at you.", "i fight", _Asker())
        self.assertEqual(_names(), ["Ghoul 1", "Ghoul 2", "Ghoul 3"])

    def test_a_door_the_player_sees_is_asked_and_files_nothing(self):
        asker = _Asker(figures=())
        _play("You see a rusted door hanging off its hinges.", "i look around", asker)
        self.assertEqual(len(asker.asked("figure_kind")), 1)
        self.assertEqual(asker.asked("figure_kind_check"), [])
        self.assertEqual(_names(), [])

    def test_the_shapes_that_show_one_present(self):
        from app import unnamed

        def read(text):
            return [(m["kind"], m["count"], m["subject"], m["seen"]) for m in unnamed.mentions(text)]

        self.assertEqual(read("You spot two raiders behind the wreck."), [("raider", 2, False, True)])
        self.assertEqual(read("You look up to face a deathclaw."), [("deathclaw", 1, False, True)])
        self.assertEqual(read("You hear a ghoul that shrieks in the dark."), [("ghoul", 1, True, False)])
        self.assertEqual(read("You meet a crowd of refugees at the gate."), [("refugee", 2, False, True)])
        # Not the player's own verb's object: "hands you", "behind you stands", "shoot at".
        self.assertEqual([k for k, *_ in read("The guard hands you a knife.")], ["guard"])
        self.assertEqual(read("Behind you stands a raider."), [])
        self.assertEqual(read("You shoot at a ghoul in the doorway."), [])

    def test_a_crowd_is_asked_as_itself(self):
        asker = _Asker(figures=())
        _play("A crowd gathers around you, muttering.", "i wait", asker)
        self.assertIn('is "crowd" a being', " ".join(asker.asked("figure_kind")))
        self.assertEqual(_names(), [])

    def test_the_figure_asks_are_capped(self):
        from app import unnamed

        prose = ("You see a ghoul, a raider, a drifter, a mutant and a robot by the gate. "
                 "You spot a deathclaw and a scorpion on the ridge.")
        asker = _Asker(figures=("ghoul", "raider", "drifter", "mutant", "robot", "deathclaw", "scorpion"))
        _play(prose, "i look around", asker)
        asks = len(asker.asked("figure_kind")) + len(asker.asked("figure_kind_check"))
        self.assertLessEqual(asks, unnamed.MAX_FIGURE_ASKS)
        self.assertEqual(len(asker.asked("figure_kind")), len(asker.asked("figure_kind_check")))


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


class ANameIsNeverAKind(unittest.TestCase):
    """The combined #33 + unnamed run: the op name 'Veyra' over 'the name Veyra' read as the kind Veyra
    ('the' two words before it) and made 'Veyra 1'. Capitalised mid-sentence is a proper name."""

    def test_capitalised_mid_sentence_is_a_name(self):
        from app.unnamed import op_kind

        self.assertEqual(op_kind("Veyra", "The words were smudged, but you could make out the name Veyra at the bottom."), "")
        self.assertEqual(op_kind("Stone", "Stone [[B]] nods."), "")

    def test_a_common_noun_is_still_a_kind(self):
        from app.unnamed import op_kind

        self.assertEqual(op_kind("Ghoul", "A ghoul lunges at you. The ghoul hisses."), "Ghoul")
        self.assertEqual(op_kind("Ghoul", "Ghouls lunge at you from the dark."), "Ghoul")
        self.assertEqual(op_kind("Raider", '"Drop it," a raider growls.'), "Raider")
