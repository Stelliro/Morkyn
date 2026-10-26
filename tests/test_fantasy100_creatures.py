"""fantasy100 (Hermes 3 8B, Thornhallow, 2026-10-26): creatures that appear only in the prose are never filed.

Fault-log F193/F199 cont., F202, and the body-part part of F163 cont. 7. The
prose and lines below are the run's own, verbatim (turns/NNN.json).

1. T75: "You crest a rise to find the direwolf crouched on a ledge ... The
   direwolf growls low in its throat": the figure asks ran on "growl",
   "rise" and "head", never on "direwolf" (a "the" form that closes on no
   one was never introduced), so no row. T76 "I swing my broom at the
   direwolf's snout": no row for the blow (attack_untargeted_no_line), and
   the draft's band die (player.health_delta 1d4 = -2) took the player 20 ->
   18 on a melee success.
2. T45: "the dark shape coming at me ... I strike at it with my broom" bound
   by the trigger to Gisela [[N]], the player's companion on record.
3. T21: "four familiar faces nod to you" -> rows Face 1..4 (the plural roll
   on a body part).
4. T58: two cloaked and hooded figures "detach from the beast": the prose's
   own two figures, filed as two (kept: no over-correction).
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-fantasy100-creatures-"))
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

T75_LINE = "I climb after the clawed foot marks into the rocks, my broom ready, and look for the direwolf."
T75_PROSE = (
    "You climb after the clawed foot marks into the rocks, following them up into the heights above Thornhallow "
    "[[L1]]. The path winds between boulders and outcroppings, twisting back on itself as it ascends. The wind is "
    "sharp with a hint of winter's chill in it. You keep your broom at the ready, scanning the rocky ledges for any "
    "sign of direwolf.\n\n"
    "After a time you hear a distant growl echoing from above. The growls sound closer now - the wolf is moving "
    "through these heights.\n\n"
    "You crest a rise to find the direwolf crouched on a ledge ahead of you, its back half-turned to you as it "
    "sniffs at something on the ground. It's easily the size of a horse, mottled grey and black fur rippling with "
    "muscle. A massive head turns slowly to look at you, glowing amber gaze fixing on your face.\n\n"
    "The direwolf growls low in its throat, hackles rising. You fumble for your broom, heart pounding as you try to "
    "remember what Master Pottle said about direwolves - something about not making direct eye contact? You lock "
    "gazes with the beast and slowly lift your broom..."
)
T76_LINE = "I swing my broom at the direwolf's snout."

T44_PROSE = (
    "You walk down the road from Thornhallow [[L1]], leaving the tower and the woodcutter Gisela [[N]]. The night "
    "is dark.\n\nThe road winds through the outskirts of town towards the ruined King's Road that cuts across these "
    "hill country ruins. You've heard rumors of some kind of creature hunting at night in the older ruins above "
    "Thornhallow [[L1]]. Maybe tonight you'll finally get a look at what it could be.\n\nAs you walk, the sounds of "
    "the tower and town fade to the quiet crunch of your boots on gravel. The occasional snap of a twig or rustle of "
    "foliage catches your attention as you scan the shadows for movement.\n\nEventually you reach the base of the "
    "hill where the older ruins begin. Crumbling columns and foundations stretch away into the darkness. A faint "
    "breeze carries the scent of wild herbs from the overgrown terraces. You pause here, getting your bearings as "
    "you decide which path up the hill to take.\n\nA flicker of movement catches your eye - something dark moving "
    "between the ruins. It seems to be heading in your direction..."
)
T45_LINE = ("I raise my Candlelight to see the dark shape coming at me and shout for it to stop; if it lunges I "
            "strike at it with my broom.")

T21_LINE = ("I leave the guild hall and walk out of Thornhallow along the old King's Road toward the ruins in the "
            "Greywold hills.")
T21_PROSE = (
    "You step out of the Chandlers' Guild hall [[L3]] into the light of a cloudy morning. The old King's Road "
    "stretches away to the south, flanked by grassy fields and distant woods. To the west, craggy grey hills rise "
    "where ruins of ancient buildings peer from behind trees. You set off towards them.\n\n"
    "The road is quiet as you walk, with only a few birdsonging and some cattle in a field nearby. As you pass "
    "through Thornhallow [[L1]]'s outskirts, four familiar faces nod to you but do not approach. After ten minutes' "
    "walk, the last buildings fall away and you are on open road alone. You follow the King's Road south for "
    "perhaps another 20 minutes before turning west onto an old track leading into the hills."
)

T58_LINE = ("I thank Ermengarde, leave the guild hall and walk out of town along the old King's Road toward the "
            "Greywold hills to look for a wolf or other beast.")
T58_PROSE = (
    "After perhaps an hour's walk, you spot movement in the deeper darkness of the hills ahead. It looks like some "
    "large creature, loping along the crest of a ridge. Your hand strays to the staff at your side.\n\n"
    "As you watch, two figures detach from the beast and descend toward you - not one wolf but two, cloaked and "
    "hooded. They draw closer and slow as they see you. One raises a hand in greeting."
)

GISELA = {"id": 14, "code": "N", "name": "Gisela", "role": "woodcutter", "kind": "", "kind_number": 0, "died_turn": 0,
          "rank": "F", "stat_profile": {}, "location_id": 8, "pronouns": "she", "sex": "female"}
DIREWOLF = {"id": 30, "code": "Z", "name": "Direwolf 1", "role": "", "kind": "Direwolf", "kind_number": 1,
            "died_turn": 0, "rank": "F", "stat_profile": {}, "location_id": 8}


def _fresh_world():
    from app import db, rng, world

    db.init_db()
    rng.reset_seed_cache()
    world.start_playthrough({"player_name": "Wren", "player_public_name": "Wren", "start_location": "Thornhallow",
                             "special_ability_origin": "none"})


class _Asker:
    """The small asks, scripted: yes for the kinds given (Hermes said yes to "face" at T21), no otherwise."""

    def __init__(self, figures=(), hostile=()):
        self.figures = {f.lower() for f in figures}
        self.hostile = {h.lower() for h in hostile}
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system, user, *, trace=None, usage=None, phase="", max_tokens=None):
        self.calls.append((phase, user))
        if phase == "figure_kind":
            return "Yes, in this" if any(f'is "{f}" a being' in user for f in self.figures) else "No, in this"
        if phase == "figure_kind_check":
            return "Yes." if any(f"is the {f} a creature or a person?" in user for f in self.figures) else "No."
        if phase == "figure_hostile":
            return 'Yes, "a' if any(h in user.lower() for h in self.hostile) else 'No, "a'
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
            "SELECT id, code, name, role, attitude, kind, kind_number, location_id FROM npcs ORDER BY id"
        ).fetchall()]


def _here_id():
    from app import db

    with db.connect().closing() as conn:
        return int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])


# --- word classes ---------------------------------------------------------------


class BodyPartsAndActNouns(unittest.TestCase):
    def test_t75_growl_and_rise_are_the_texts_own_verbs_head_is_a_body_part(self):
        from app import unnamed

        stems = unnamed._verb_stems(T75_PROSE)
        self.assertEqual(unnamed.no_body("growl", stems), "act noun")   # "The direwolf growls low"
        self.assertEqual(unnamed.no_body("rise", stems), "act noun")    # "hackles rising"
        self.assertEqual(unnamed.no_body("head", stems), "body part")   # "A massive head turns"
        self.assertEqual(unnamed.no_body("faces", stems), "body part")  # T21
        self.assertEqual(unnamed.no_body("direwolf", stems), "")

    def test_a_creature_is_no_act_noun(self):
        from app import unnamed

        prose = "A ghoul lunges at you. Two more ghouls follow, snarling. A raider fires; the wolf bit you."
        stems = unnamed._verb_stems(prose)
        for kind in ("ghoul", "raider", "wolf"):
            self.assertEqual(unnamed.no_body(kind, stems), "", kind)

    def test_present_kinds_has_the_crouched_direwolf_not_the_head_or_the_growl(self):
        from app import unnamed

        present = unnamed.present_kinds(T75_PROSE)
        self.assertIn("direwolf", present)
        self.assertFalse({"head", "growl", "rise", "face"} & present)
        # Attacking is a narrower set: the wolf closed on no one at T75.
        self.assertNotIn("direwolf", unnamed.shown_kinds(T75_PROSE))


# --- 1. the direwolf is filed (T75) and the blow lands on it (T76) ---------------


class TheDirewolfIsFiled(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_t75_files_direwolf_1_and_asks_nothing_about_growl_rise_head(self):
        asker = _Asker(figures=("direwolf",))
        _play(T75_PROSE, T75_LINE, asker)
        rows = [r for r in _rows() if r["kind"]]
        self.assertEqual([(r["name"], r["kind"], r["kind_number"]) for r in rows], [("Direwolf 1", "Direwolf", 1)])
        self.assertEqual(rows[0]["location_id"], _here_id())
        asked = " ".join(asker.asked("figure_kind"))
        self.assertIn('is "direwolf" a being', asked)
        for word in ("growl", "rise", "head"):
            self.assertNotIn(f'"{word}"', asked)

    def test_t75_the_direwolf_is_the_same_row_next_turn(self):
        _play(T75_PROSE, T75_LINE, _Asker(figures=("direwolf",)))
        _play("The direwolf growls low in its throat. It circles warily around you.", "I hold my ground.", _Asker())
        self.assertEqual([r["name"] for r in _rows() if r["kind"]], ["Direwolf 1"])

    def test_t75_no_row_when_the_asks_say_no(self):
        _play(T75_PROSE, T75_LINE, _Asker())
        self.assertEqual([r["name"] for r in _rows() if r["kind"]], [])

    def test_a_the_noun_the_player_never_named_is_still_not_introduced(self):
        # "The direwolf growls" alone, the player's line about something else: a "the" refers back.
        asker = _Asker(figures=("direwolf",))
        _play(T75_PROSE, "I climb into the rocks and keep my broom ready.", asker)
        self.assertEqual([r["name"] for r in _rows() if r["kind"]], [])
        self.assertNotIn('"direwolf"', " ".join(asker.asked("figure_kind")))

    def test_t76_the_blow_mints_the_wolf_the_last_prose_showed_and_lands_on_it(self):
        from app import attack_intent as A
        from app import db, entity_kinds, unnamed

        ctx = {"current_location": {"id": _here_id(), "code": "L1", "npcs": [GISELA]}, "npcs": [GISELA],
               "last_narration": T75_PROSE}
        asker = _Asker(figures=("direwolf",))
        previous = entity_kinds.set_kind_ask(asker)

        def minter(kind):
            with db.connect().closing() as conn:
                shell = unnamed.mint_shown(conn, T75_PROSE, kind, _here_id(), call=entity_kinds._call, line=T76_LINE)
                conn.commit()
            return shell

        try:
            inferred = {"skill_code": "melee", "weapon_or_tool": "broom"}
            check, report = A.decide(f"Player: {T76_LINE}", ctx, inferred, lambda *a, **k: "No", minter=minter)
        finally:
            entity_kinds.set_kind_ask(previous)
        self.assertEqual(report.get("from"), "minted")
        self.assertEqual(report.get("unknown_noun"), "direwolf")
        self.assertEqual(check["attack"]["name"], "Direwolf 1")
        self.assertEqual([r["name"] for r in _rows() if r["kind"]], ["Direwolf 1"])
        # Gisela is never asked about: the blow had its target before the asks.
        self.assertEqual(report.get("asks"), [])

    def test_t76_with_the_row_filed_the_blow_is_at_it_by_kind(self):
        from app import attack_intent as A

        ctx = {"current_location": {"id": 8, "code": "L8", "npcs": [GISELA, DIREWOLF]}, "npcs": [GISELA, DIREWOLF],
               "last_narration": T75_PROSE}
        minted = []
        inferred = {"skill_code": "melee"}
        check, report = A.decide(f"Player: {T76_LINE}", ctx, inferred, lambda *a, **k: "No",
                                 minter=lambda k: minted.append(k))
        self.assertEqual((report.get("from"), check["attack"]["code"]), ("kind", "Z"))
        self.assertEqual(minted, [])

    def test_a_named_person_attacked_by_code_still_binds(self):
        from app import attack_intent as A

        ctx = {"current_location": {"id": 8, "code": "L8", "npcs": [GISELA]}, "npcs": [GISELA],
               "last_narration": T75_PROSE}
        for line in ("I swing my broom at @N.", "I swing my broom at Gisela."):
            minted = []
            inferred = {"skill_code": "melee", "npc_ref": {"code": "N", "name": "Gisela"}}
            check, report = A.decide(f"Player: {line}", ctx, inferred, None, minter=lambda k: minted.append(k))
            self.assertEqual((report.get("from"), report.get("target")), ("trigger", {"code": "N", "name": "Gisela"}),
                             line)
            self.assertEqual(minted, [], line)

    def test_the_present_creature_is_no_word_for_someone_here(self):
        from app import attack_intent as A

        hunter = {**GISELA, "role": "direwolf hunter"}
        self.assertEqual(A.present_creature(T76_LINE, [GISELA], T75_PROSE), "direwolf")
        # A word for a person present (their job) is them, as before.
        self.assertEqual(A.present_creature("I swing my broom at the woodcutter.", [GISELA],
                                            T75_PROSE + " The woodcutter watches."), "")
        self.assertEqual(A.present_creature(T76_LINE, [GISELA], ""), "")
        self.assertEqual(A.present_creature("I swing my broom at the head.", [GISELA], T75_PROSE), "")
        # A word of someone's job is a word for them (shifts' job family): the old rule, kept.
        self.assertEqual(A.present_creature(T76_LINE, [hunter], T75_PROSE), "")


# --- 2. the blow at a dark shape is not at the companion (T45) --------------------


class TheShapeIsNotTheCompanion(unittest.TestCase):
    def _ctx(self, party):
        ctx = {"current_location": {"id": 8, "code": "L8", "npcs": [GISELA]}, "npcs": [GISELA],
               "last_narration": T44_PROSE}
        if party:
            ctx["party"] = [{"id": 1, "npc_id": 14, "npc_name": "Gisela", "role": "companion"}]
        return ctx

    def test_t45_the_trigger_does_not_bind_the_blow_to_gisela(self):
        from app import attack_intent as A

        inferred = {"skill_code": "melee", "npc_ref": {"code": "N", "name": "Gisela"}}
        check, report = A.decide(f"Player: {T45_LINE}", self._ctx(True), inferred, None, minter=lambda k: None)
        self.assertIsNone(check)
        self.assertIsNone(report.get("target"))
        self.assertEqual(report.get("not_the_lines", {}).get("code"), "N")
        self.assertIsNone(inferred.get("attack"))
        self.assertIsNone(inferred.get("npc_ref"))

    def test_the_companion_flag_comes_from_the_party_record(self):
        from app import attack_intent as A

        self.assertTrue(A.people_here(self._ctx(True))[0].get("in_party"))
        self.assertFalse(A.people_here(self._ctx(False))[0].get("in_party"))

    def test_without_the_party_record_the_old_rule_stands(self):
        # One person present and a word for someone: the person, as 4833150 decided.
        from app import attack_intent as A

        inferred = {"skill_code": "melee", "npc_ref": {"code": "N", "name": "Gisela"}}
        check, report = A.decide(f"Player: {T45_LINE}", self._ctx(False), inferred, None, minter=lambda k: None)
        self.assertEqual(report.get("from"), "trigger")

    def test_the_companion_named_is_still_the_target(self):
        from app import attack_intent as A

        inferred = {"skill_code": "melee", "npc_ref": {"code": "N", "name": "Gisela"}}
        check, report = A.decide("Player: I strike at Gisela with my broom.", self._ctx(True), inferred, None,
                                 minter=lambda k: None)
        self.assertEqual(report.get("target"), {"code": "N", "name": "Gisela"})


# --- 3. faces are no one (T21) -------------------------------------------------------


class FacesAreNoOne(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_t21_four_familiar_faces_file_no_rows_and_spend_no_ask(self):
        asker = _Asker(figures=("face",))  # Hermes said yes to both asks at T21
        _play(T21_PROSE, T21_LINE, asker)
        self.assertEqual([r["name"] for r in _rows() if r["kind"]], [])
        self.assertNotIn('"face"', " ".join(asker.asked("figure_kind")))

    def test_a_face_row_an_older_save_holds_is_not_added_to(self):
        from app import db, unnamed

        with db.connect().closing() as conn:
            unnamed.mint(conn, _here_id(), "Face", person=False)
            conn.commit()
        _play(T21_PROSE, T21_LINE, _Asker(figures=("face",)))
        self.assertEqual([r["name"] for r in _rows() if r["kind"]], ["Face 1"])


# --- 4. the prose's own two figures stay two (T58, no over-correction) ----------------


class TheProsesFiguresStay(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_t58_two_cloaked_figures_are_two_rows(self):
        _play(T58_PROSE, T58_LINE, _Asker())
        names = [r["name"] for r in _rows() if r["kind"]]
        self.assertEqual(len(names), 2, names)
        self.assertTrue(all(n.startswith("Figure ") for n in names), names)


# --- 5. a blow at nothing on record takes no health from the band (T76 as recorded) ---


class NoBandDamageWithoutAnAttacker(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def _result(self, **check):
        return {
            "player": {"health_delta": -2},
            "skill_checks": [{"skill": {"code": "melee", "name": "Melee"}, "natural": 15, "outcome": "success", **check}],
        }

    def _void(self, result):
        from app import db, world

        with db.connect().closing() as conn:
            return world._void_untargeted_blow_health(conn, result, {})

    def test_t76_untargeted_success_voids_the_band_damage(self):
        result = self._result()
        self.assertTrue(self._void(result))
        self.assertEqual(result["player"]["health_delta"], 0)

    def test_a_target_or_a_hostile_here_keeps_it(self):
        result = self._result(attack={"code": "Z", "name": "Direwolf 1"})
        self.assertFalse(self._void(result))
        self.assertEqual(result["player"]["health_delta"], -2)
        from app import db, unnamed

        with db.connect().closing() as conn:
            unnamed.mint(conn, _here_id(), "Direwolf", attitude="hostile", person=False)
            conn.commit()
        result = self._result()
        self.assertFalse(self._void(result))
        self.assertEqual(result["player"]["health_delta"], -2)

    def test_the_rolls_own_mishap_and_a_turn_with_no_attack_keep_it(self):
        result = {**self._result(), "_server_authored": ["player.health_delta"]}
        self.assertFalse(self._void(result))
        result = {"player": {"health_delta": -2}, "skill_checks": [
            {"skill": {"code": "perception"}, "natural": 12, "outcome": "success"}]}
        self.assertFalse(self._void(result))
        result = {**self._result(), "_figures": {"direwolf": {"figure": True, "hostile": True, "by": "ask"}}}
        self.assertFalse(self._void(result))


if __name__ == "__main__":
    unittest.main()
