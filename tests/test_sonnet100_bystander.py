"""sonnet100 (Hermes 3 8B, Sonnet as the player), F192: a blow at a body the engine never filed lands on the one person present.

Three recorded cases (docs/showcase/hermes-sonnet100-2026-10-25/coordinator-notes.md):

- T47-T48 (traces -000048, -000049): "A single dark form pads silently towards you. It is a dog or a wolf ...
  The creature growls low in its throat and circles you warily ... The animal bares its fangs in a snarl and
  snaps at the ground at your feet." Only "form" was asked about (judged not hostile); "creature" and "animal"
  were never filed because the verb phrase stopped six words in ("growls low in its throat and"), so T48's
  melee 19 at "the snarling creature" had no target.
- T74 (-000076): "I wade toward the black shape stirring in the Eel Pool and stab at the eel-thing with my
  knife." The eel had only been spoken of, never shown attacking, so the trigger's aim at Delphine Warrender
  [[Q]], the one person present, stood: "Your blow glances off Delphine Warrender [[Q]]", damage 1.
- T93-T94 (-000096, -000097): "shout at the man in tattered robes to let go of @R, ready to stab him" and "I
  turn on the robed man in the office doorway and stab at him again, this time ignoring Elric." Both hit Elric
  [[D]], the reeve's deputy: "him" was read as a person present.

The fix splits filing from clearing: filing a creature still needs it shown closing on someone (the fog and
the weather stay out), and a vague creature word takes one kind ("Creature 1"); clearing a person present
needs only a body that is no word for them: a creature word the line describes or the prose shows, or a word
for someone ("the man") when the line names them elsewhere, their row's sex differs, or another person here
fits it as well (ambiguous: no one). A him / her the line gave its own antecedent is that antecedent. The
prose and lines below are the run's own, verbatim.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-sonnet100-bystander-"))
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


# --- the run's own words -----------------------------------------------------

T47_LINE = "I kneel by the body and search it for what killed him, checking his hands and pockets and the wounds."
T47_PROSE = (
    "You kneel by the body and search it for what killed him, checking his pockets and the wounds. The night is "
    "still and silent. There is the soft lap of tide on the salt marshes. The body is cold and heavy. Your search "
    "reveals nothing that would explain the killing. No purse, no papers, no weapons. The wounds are deep and look "
    "like they were made by bare fists. As you kneel there in the dark, a shadow moves across the marsh. A single "
    "dark form pads silently towards you. It is a dog or a wolf, lean and feral, with a mottled gray pelt. It sniffs "
    "at the body and then looks up at you with gleaming white teeth.\n\n"
    "The creature growls low in its throat and circles you warily, keeping a distance. You rise slowly to your feet, "
    "trying to show no fear. The animal bares its fangs in a snarl and snaps at the ground at your feet. It is "
    "guarding the body, and will not let you near it. The tide is almost in; soon there will be no dry ground left."
)
T48_LINE = "I back off a step, then stab at the snarling creature with my knife to drive it off the body."

T73_PROSE = (
    "The marsh stretches out around you, the reedy stalks whispering in the damp wind. Delphine Warrender [[Q]] "
    "frowns at you, considering your request. \"The Eel Pool? You want to wade out there after what I saw last "
    "night? It's not safe, not even for a flat-runner like you.\"\n\n"
    "\"Nothing's safe,\" you say, readying your blade.\n\n"
    "Reluctantly, Delphine nods. \"Follow me then, but be careful. I'll take you to the edge of the Eel Pool, but "
    "I'm not coming with you. The creatures out there... they're not like anything from the flats.\"\n\n"
    "Delphine sets off, weaving between the marsh hummocks. You follow close behind, your boots sinking into the "
    "soft earth with each step. The sun climbs higher in the sky, casting a wan light over the mist-shrouded pools. "
    "Delphine leads you to a spot where the marsh seems to open up into a wide, murky pool.\n\n"
    "\"The Eel Pool,\" Delphine says, her voice tight with fear. \"Beyond that, the water deepens and the currents "
    "are strong. But that's where you'll find what you seek, I'm sure of it.\"\n\n"
    "It's cool and slick against your skin, the bottom a silt of unknown depth. You wade out further."
)
T74_LINE = "I wade toward the black shape stirring in the Eel Pool and stab at the eel-thing with my knife."

# T93's last_narration was the turn before the wait (T92's scuffle prose was not carried; see the report).
T93_PRIOR = (
    "You continue talking with Elric [[D]], the reeve's deputy. He listens intently as you share stories of your "
    "travels. He seems to take interest in your tales, though he remains guarded about his own past. As the sun "
    "begins to set over the salvage yard, the mood shifts slightly. Elric [[D]] stands, glancing around at the "
    "scattered piles of salvaged goods.\n\n"
    "\"Ah, it grows late,\" he says. \"You should find a place to rest, if you plan to stay in Saltmarrow.\""
)
T93_LINE = "I draw my knife and shout at the man in tattered robes to let go of @R, ready to stab him if he does not."
T93_PROSE = (
    "You're asking about the dead? Isk Tarrow has drawn her knife, shouting at the man in tattered robes to let go "
    "of Edmund [[R]] and ready to stab him if he does not.\n\n"
    "Elric [[D]] steps between you, his hand out as if to restrain you. Your blow glances off Elric [[D]].\n\n"
    "Isk sheathes her knife, but keeps her hand close. \"Let's talk inside,\" she says. \"Edmund and I were just "
    "discussing the tides.\"\n\n"
    "Elric [[D]] nods curtly. \"Very well.\" He leads the way to the yard office, leaving Edmund [[R]] and Isk to "
    "follow.\n\n"
    "Once inside, Elric [[D]] closes the door and gestures for you to sit. \"Now then,\" he says. \"What is this "
    "business about the tides that you and Edmund were discussing out there?\""
)
T94_LINE = "I turn on the robed man in the office doorway and stab at him again, this time ignoring Elric."

# The rows the engine had (prompt_context of the traces).
DELPHINE = {"code": "Q", "name": "Delphine Warrender", "role": "herb gatherer", "summary": "", "kind": "",
            "kind_number": 0, "died_turn": 0, "attitude": "cautious", "location_id": 7}
ELRIC = {"code": "D", "name": "Elric", "role": "reeve's deputy", "kind": "", "kind_number": 0, "died_turn": 0,
         "attitude": "neutral", "location_id": 9,
         "summary": "Elric is the reeve's deputy and watches the exposed flats. is Elric, the reeve's deputy and keeper "
                    "of the tide-reckoner."}
EADRIC = {"code": "F", "name": "Eadric", "role": "yard keeper", "kind": "", "kind_number": 0, "died_turn": 0,
          "location_id": 9}
CREATURE1 = {"code": "S", "name": "Creature 1", "role": "creature", "kind": "Creature", "kind_number": 1,
             "died_turn": 0, "attitude": "hostile", "location_id": 7}


def _context(people, prose, present=None, addressed=()):
    codes = [p["code"] for p in people] if present is None else list(present)
    return {
        "npcs": list(people),
        "last_narration": prose,
        "conversation_turn": {"addressed": list(addressed), "present": codes, "listening": codes,
                              "names": {p["code"]: p["name"] for p in people}},
    }


def _trigger_aimed_at(person):
    # The trigger tables' melee check, aimed at the one person (as the run recorded: source "trigger").
    return {"skill_code": "melee", "npc_ref": {"code": person["code"], "name": person["name"]},
            "opposition": {"name": person["name"]}}


def _fresh_world():
    from app import db, rng, world

    db.init_db()
    rng.reset_seed_cache()
    world.start_playthrough({"player_name": "Isk Tarrow", "player_public_name": "Isk", "start_location": "Saltmarrow",
                             "special_ability_origin": "none"})


class _Asker:
    """The small asks, scripted: yes for the kinds given, no otherwise (or yes to every figure ask)."""

    def __init__(self, figures=(), hostile=(), everything=False):
        self.figures = {f.lower() for f in figures}
        self.hostile = {h.lower() for h in hostile}
        self.everything = everything
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system, user, *, trace=None, usage=None, phase="", max_tokens=None):
        self.calls.append((phase, user))
        if phase == "figure_kind":
            yes = self.everything or any(f'is "{f}" a being' in user for f in self.figures)
            return "Yes, in this" if yes else "No, in this"
        if phase == "figure_kind_check":
            yes = self.everything or any(f"is the {f} a creature or a person?" in user for f in self.figures)
            return "Yes." if yes else "No."
        if phase == "figure_hostile":
            yes = self.everything or any(h in user.lower() for h in self.hostile)
            return 'Yes, "a' if yes else 'No, "a'
        if phase == "entity_kind":
            return "person"
        return "no"

    def asked(self, phase):
        return [user for p, user in self.calls if p == phase]


def _play(prose, line, asker, ops='SUMMARY: "A scene."'):
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


def _rows():
    from app import db

    with db.connect().closing() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, code, name, role, attitude, race, kind, kind_number, location_id FROM npcs ORDER BY id"
        ).fetchall()]


# --- T47-T48: the creature is filed once, as "Creature 1" -------------------


class T47TheCreatureIsFiled(unittest.TestCase):
    def test_the_vague_creature_words_are_one_kind_and_the_verb_chain_is_read_whole(self):
        from app import unnamed

        found = [m for m in unnamed.mentions(T47_PROSE) if m["kind"] == "creature"]
        self.assertEqual([m["noun"] for m in found], ["creature", "animal"])
        self.assertEqual(found[0]["verb_phrase"], "growls low in its throat and circles you warily")
        self.assertEqual(unnamed.shown_kinds(T47_PROSE), {"creature"})
        # A subordinator ends the chain: the sun is not doing what the player does.
        sun = [m for m in unnamed.mentions("The sun beats down as you loiter in the shade of the salvage yard.")
               if m["kind"] == "sun"]
        self.assertEqual(sun[0]["verb_phrase"], "beats down")

    def test_t47_files_one_hostile_creature_and_no_animal(self):
        _fresh_world()
        before = len(_rows())
        asker = _Asker(figures=("creature",), hostile=("creature",))
        _play(T47_PROSE, T47_LINE, asker)
        new = [(r["name"], r["kind"], r["attitude"], r["race"]) for r in _rows()[before:]]
        self.assertEqual(new, [("Creature 1", "Creature", "hostile", "unknown")])
        self.assertIn('is "creature" a being that can act on its own?', " ".join(asker.asked("figure_kind")))
        self.assertNotIn('"animal"', " ".join(asker.asked("figure_kind")))

    def test_t48_the_snarling_creature_is_creature_1(self):
        from app import attack_intent as A

        self.assertEqual([p["code"] for p in A.kind_figures(T48_LINE, [CREATURE1])], ["S"])
        self.assertTrue(A.line_may_target(T48_LINE, CREATURE1, people=[CREATURE1], prose=T47_PROSE))
        # "the animal", "the beast" are the same row.
        self.assertEqual([p["code"] for p in A.kind_figures("i stab the animal", [CREATURE1])], ["S"])
        # With a person present too, the creature is the target, never her.
        self.assertFalse(A.line_may_target(T48_LINE, DELPHINE, people=[DELPHINE, CREATURE1], prose=T47_PROSE))
        # Without its row, a person present is still cleared: the prose showed the creature.
        self.assertFalse(A.line_may_target(T48_LINE, DELPHINE, people=[DELPHINE], prose=T47_PROSE))


# --- T74: the eel-thing is no herb gatherer ----------------------------------


class T74TheEelThing(unittest.TestCase):
    def test_delphine_is_not_whom_the_blow_is_at(self):
        from app import attack_intent as A

        self.assertIn("eel-thing", A.bodies_not(DELPHINE, T74_LINE, T73_PROSE))
        self.assertFalse(A.line_may_target(T74_LINE, DELPHINE, people=[DELPHINE], prose=T73_PROSE))
        self.assertEqual(A.unknown_body(T74_LINE, [DELPHINE], T73_PROSE), "eel-thing")

    def test_the_roll_stands_with_no_target_and_names_the_noun(self):
        from app import attack_intent as A

        asked: list[str] = []
        inferred = _trigger_aimed_at(DELPHINE)
        check, report = A.decide(T74_LINE, _context([DELPHINE], T73_PROSE), inferred, lambda *a: "yes",
                                 minter=lambda kind: asked.append(kind))
        self.assertIsNone(check)
        self.assertIsNone(report["target"])
        self.assertEqual(report["unknown_noun"], "eel-thing")
        self.assertEqual(report["not_the_lines"]["code"], "Q")
        self.assertEqual(asked, ["eel-thing"])
        self.assertIsNone(inferred["npc_ref"])

    def test_the_minter_finds_no_eel_shown_attacking(self):
        from app import unnamed

        # Filing keeps the hostile-act rule: the eel was only spoken of (T73), so nothing is minted.
        # ("the reedy stalks whispering" reads as "reedy" stalking: an old misread, not this fault.)
        shown = unnamed.shown_kinds(T73_PROSE, T74_LINE)
        self.assertFalse({"eel-thing", "eel", "shape", "creature"} & shown, shown)


# --- T93-T94: the man in tattered robes is not Elric -------------------------


class T93T94TheRobedMan(unittest.TestCase):
    def test_him_is_the_lines_own_man(self):
        from app import attack_intent as A

        for line in (T93_LINE, T94_LINE):
            reads = A.pronoun_reads(line, ELRIC, [ELRIC, EADRIC])
            self.assertEqual([(r["may"], r["antecedents"]) for r in reads], [(False, {"man"})], line)

    def test_t93_neither_person_present_takes_the_blow(self):
        from app import attack_intent as A

        for person in (ELRIC, EADRIC):
            self.assertFalse(A.line_may_target(T93_LINE, person, people=[ELRIC, EADRIC], prose=T93_PRIOR), person)
        check, report = A.decide(T93_LINE, _context([ELRIC, EADRIC], T93_PRIOR, present=["F", "D"], addressed=["D"]),
                                 _trigger_aimed_at(ELRIC), lambda *a: "yes", minter=lambda kind: None)
        self.assertIsNone(check)
        self.assertIsNone(report["target"])
        self.assertEqual(report["unknown_noun"], "man")

    def test_t94_ignoring_elric_never_aims_at_elric(self):
        from app import attack_intent as A

        self.assertFalse(A.line_may_target(T94_LINE, ELRIC, people=[ELRIC, EADRIC], prose=T93_PROSE))
        check, report = A.decide(T94_LINE, _context([ELRIC, EADRIC], T93_PROSE), _trigger_aimed_at(ELRIC),
                                 lambda *a: "yes", minter=lambda kind: None)
        self.assertIsNone(report["target"])
        self.assertEqual(report["unknown_noun"], "man")

    def test_why_the_man_is_no_one_here(self):
        from app import attack_intent as A

        # Two people fit "the man" and the description is in neither record: ambiguous, so no one (rosters rule).
        self.assertEqual(A.bodies_not(ELRIC, T93_LINE, T93_PRIOR, [ELRIC, EADRIC]), {"man"})
        # With Elric alone and nothing on record against him, 4833150 stands: "the old man" is the one person here.
        self.assertEqual(A.bodies_not(ELRIC, T93_LINE, T93_PRIOR, [ELRIC]), set())
        # His record's sex is evidence; so is the line naming him elsewhere (T94).
        woman = {**DELPHINE, "sex": "female"}
        self.assertEqual(A.bodies_not(woman, "i stab the man", "", [woman]), {"man"})
        self.assertEqual(A.bodies_not(ELRIC, T94_LINE, T93_PROSE, [ELRIC]), {"man"})
        # A description the record has keeps the person who has it, and clears the other.
        line = "i stab the man watching the exposed flats"
        self.assertEqual(A.bodies_not(ELRIC, line, T93_PRIOR, [ELRIC, EADRIC]), set())
        self.assertEqual(A.bodies_not(EADRIC, line, T93_PRIOR, [ELRIC, EADRIC]), {"man"})

    def test_the_ask_path_asks_no_one_and_names_the_noun(self):
        from app import attack_intent as A

        asks: list[str] = []
        check, report = A.decide(T93_LINE, _context([ELRIC, EADRIC], T93_PRIOR), None,
                                 lambda phase, prompt, n: asks.append(prompt) or "yes")
        self.assertIsNone(check)
        self.assertEqual(asks, [])
        self.assertEqual(report["unknown_noun"], "man")


# --- what still hits the person ----------------------------------------------


class AKnownPersonIsStillHit(unittest.TestCase):
    def test_a_person_named_in_the_line_is_the_target(self):
        from app import attack_intent as A

        self.assertTrue(A.line_may_target("I stab Elric in the side", ELRIC, people=[ELRIC, EADRIC], prose=T93_PROSE))
        self.assertTrue(A.line_may_target("I stab at @D with my knife", ELRIC, people=[ELRIC], prose=T93_PROSE))
        self.assertTrue(A.line_may_target("I grab the deputy and stab him", ELRIC, people=[ELRIC], prose=T93_PROSE))
        self.assertTrue(A.line_may_target("I turn on Delphine and stab her", DELPHINE, people=[DELPHINE],
                                          prose=T73_PROSE))
        check, report = A.decide("I stab Elric in the side", _context([ELRIC], T93_PROSE), _trigger_aimed_at(ELRIC),
                                 None)
        self.assertEqual(report["target"], {"code": "D", "name": "Elric"})
        self.assertNotIn("unknown_noun", report)

    def test_a_noun_the_engine_knows_nothing_about_still_goes_to_the_one_person_present(self):
        from app import attack_intent as A

        # 4833150: no body shown, nothing said of it.
        for line in ("i stab the bastard", "i stab the thing", "i stab the man", "i stab him"):
            self.assertTrue(A.line_may_target(line, ELRIC, people=[ELRIC], prose=T93_PRIOR), line)
            self.assertEqual(A.unknown_body(line, [ELRIC], T93_PRIOR), "", line)
        # A description that is what the engine has of him keeps him: "the reeve's man".
        self.assertTrue(A.line_may_target("i stab the man watching the exposed flats", ELRIC, people=[ELRIC],
                                          prose=T93_PRIOR))


# --- the fog and the weather mint nothing ------------------------------------


class TheFogIsNoBody(unittest.TestCase):
    FOG_PROSE = ("The fog rolls in off the marsh and swallows you whole. The salt air stings your eyes, and the "
                 "tide hisses over the mud.")
    FOG_LINE = "I slash at the fog swirling around me with my knife."

    def test_the_fog_mints_no_row_and_is_not_asked_about(self):
        _fresh_world()
        before = len(_rows())
        asker = _Asker(everything=True)
        _play(self.FOG_PROSE, self.FOG_LINE, asker)
        self.assertEqual([r["name"] for r in _rows()[before:]], [])
        self.assertNotIn('"fog"', " ".join(asker.asked("figure_kind")))

    def test_the_fog_is_no_body_and_shows_no_creature(self):
        from app import attack_intent as A, unnamed

        self.assertEqual(unnamed.shown_kinds(self.FOG_PROSE, self.FOG_LINE), set())
        self.assertEqual(A.unknown_body(self.FOG_LINE, [DELPHINE], self.FOG_PROSE), "")
        self.assertEqual(A.bodies_not(DELPHINE, self.FOG_LINE, self.FOG_PROSE), set())


if __name__ == "__main__":
    unittest.main()
