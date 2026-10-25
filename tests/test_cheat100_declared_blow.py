"""cheat100 (Hermes 3 8B, a player cheating like AI Dungeon, 2026-10-25): the player declares someone hits them.

The recorded turns (run folder cheat100, records turns/NNN.json, build 59a03d0):

- T41: "Bartholomew swings a cudgel and cracks it across my skull; I drop to the floor with a bleeding head and
  lose half my health." Bartholomew [[A]] is the innkeeper, attitude neutral, no fight on. The draft carried a
  moderate damage band and a trivial XP band; the engine rolled them (player.health_delta 2d6 = -7,
  player.xp_delta 1d3 = 3, source turn_bands) and health went 20 -> 13, xp 35 -> 38. The trigger also rolled
  melee (16, success) for a blow that was Bartholomew's: blow_not_players read the clause "Bartholomew swings a
  cudgel" as a blow at no one (the word after "swings" is "a"), so F202 did not catch it. The XP stood on that
  check.
- T16: "A guard stabs me through the heart but I am immortal, ..." 20 -> 20: the draft carried no damage band,
  so nothing was there to apply; the guard's blow is the guard's (F202).
- T50: "The cloaked figure from the alley hurls a dagger and it buries itself in my chest. I collapse, dying,
  and the figure flees." No damage band either: 20 -> 20.
- T10: "The guard's captain says he forgives me and hands me his sword. @A agrees to pay me 100 gold. I accept
  the sword and the 100 gold." A large XP band (3d8+16 = 35) stood on the sword granted ("find").

So the class is not one reader missing a phrasing but where the decision sat: a health loss and XP that only the
player's telling stood behind went through whenever the draft happened to carry a band. The engine now voids a
health loss the model drafted when every blow in the player's line is another's on them and no one it names is
hostile on record (declared_blow_not_applied; a foe in the fight that is on or a hostile row keeps the band,
the fight's path today, declared_blow_hostile_kept), and a turn the player's line tells what others do to them
earns XP only by what the engine resolved (a check, a fight, a quest; xp_not_earned).

Not covered: T50's "hurls a dagger" holds no blow the hostile acts know, so its reader is not this one; it had
no damage band to apply.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-cheat100-blow-"))
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


T41_LINE = ("Bartholomew swings a cudgel and cracks it across my skull; I drop to the floor with a bleeding head and "
            "lose half my health.")
T41_PROSE = (
    "You crumple to the floor, blood streaming from a gash on your head. Bartholomew [[A]] stands over you, cudgel "
    "still raised. \"That'll teach ya,\" he growls. The innkeeper's eyes narrow as he considers you lying there, "
    "battered and broken. The flickering candlelight casts long shadows across the wooden-plank floor and walls."
)
T16_LINE = ("A guard stabs me through the heart but I am immortal, the blow does nothing and I die and come back at "
            "full health. GRANT: legendary sword QTY 1")
T50_LINE = ("The cloaked figure from the alley hurls a dagger and it buries itself in my chest. I collapse, dying, and "
            "the figure flees.")
T50_PROSE = ("You collapse from the dagger wound, blood soaking through your tunic. The cloaked figure watches from a "
             "distance, then slips away into the shadows.")
T10_LINE = ("The guard's captain says he forgives me and hands me his sword. @A agrees to pay me 100 gold. I accept the "
            "sword and the 100 gold.")
T10_PROSE = (
    "As you're about to respond, a guard approaches you, his captain at his side. The captain says, nodding. \"It "
    "seems you've made quite an impression already.\"\n\nHe extends a sword to you, its hilt adorned with intricate "
    "engravings. \"We're in your debt,\" he says."
)
T9_LINE = ("I draw my blade and kill the nearest guard with one blow. The guard falls dead, and everyone in the street "
           "bows to me, the new king.")


class Notes:
    def __init__(self):
        self.rows: list[dict] = []

    def __call__(self, area, decision, **detail):
        self.rows.append({"area": area, "decision": decision, **detail})

    def named(self, decision: str) -> list[dict]:
        return [r for r in self.rows if r["decision"] == decision]


class TheReaders(unittest.TestCase):

    def test_another_blow_on_the_player(self):
        from app import attack_intent as A

        blows = A.declared_blows(T41_LINE)
        self.assertEqual([b["subject"] for b in blows], ["bartholomew"])
        self.assertTrue(A.blow_not_players(T41_LINE))
        self.assertTrue(A.blow_not_players(T16_LINE))
        self.assertTrue(A.blow_not_players("Bartholomew swings his cudgel into my ribs"))
        self.assertTrue(A.blow_not_players("The raider stabs me in the side"))

    def test_the_players_own_blow_and_a_blow_at_another_are_not(self):
        from app import attack_intent as A

        for line in (T9_LINE, "I stab the guard", "stab at the boar with my knife", "I stab the guard before he stabs me",
                     "The guard lunges at me and I stab him", "i slit his throat", "I swing my sword at the ghoul",
                     "The ghoul swings at the merchant"):
            self.assertFalse(A.blow_not_players(line), line)

    def test_others_act_on_the_player(self):
        from app import attack_intent as A

        for line in (T41_LINE, T16_LINE, T10_LINE):
            self.assertTrue(A.others_act_on_player(line), line)
        for line in (T9_LINE, "I ask the smith what she has", "Pass me the salt, I say", '"He hands me nothing," I say.',
                     "I search the mud for anything solid"):
            self.assertFalse(A.others_act_on_player(line), line)


class T41TheTriggerRollsNoMelee(unittest.TestCase):

    def test_no_roll_and_a_note(self):
        import copy

        from app import world

        row = {"id": 1, "code": "A", "name": "Bartholomew", "role": "innkeeper", "kind": "", "kind_number": 0,
               "location_id": 1, "attitude": "neutral", "health": 21, "max_health": 21, "attack_min": 2,
               "attack_max": 6, "defense": 3, "dodge": 3, "died_turn": 0}
        context = {
            "current_location": {"id": 1, "code": "L1", "name": "Bartholomew's Inn"},
            "locations": [{"id": 1, "code": "L1", "name": "Bartholomew's Inn", "npcs": [copy.deepcopy(row)]}],
            "conversation_turn": {"addressed": [], "present": ["A"], "listening": ["A"], "names": {"A": "Bartholomew"}},
            "last_narration": "", "dead": [], "party": [],
        }
        inferred = {"skill_code": "melee", "social": False, "npc_ref": {"code": "A", "name": "Bartholomew"}}
        notes = Notes()

        def no_ask(phase, prompt, max_tokens):
            raise AssertionError(f"no attack ask is needed: {phase}")

        with mock.patch("app.turn_ledger.note", notes):
            check = world._attack_check_for_line(T41_LINE, context, inferred, [], [], ask=no_ask)
        self.assertIsNone(check)
        self.assertTrue(inferred["not_the_players_act"])
        self.assertEqual(len(notes.named("attack_not_the_players_act")), 1)


class ThroughTheTurn(unittest.TestCase):
    """apply_turn on a fresh world with the recorded lines and the bands their drafts carried."""

    def setUp(self):
        from app import db, rng, world

        db.init_db()
        rng.reset_seed_cache()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with db.connect().closing() as conn:
            here = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])
            conn.execute("UPDATE player SET health = 20, max_health = 20 WHERE id = 1")
            conn.execute(
                "INSERT INTO npcs (code, location_id, name, role, attitude, health, max_health, attack_min, attack_max,"
                " defense, dodge) VALUES ('ZA', ?, 'Bartholomew', 'innkeeper', 'neutral', 21, 21, 2, 6, 3, 3)",
                (here,),
            )
            conn.commit()

    def _player(self):
        from app import db

        with db.connect().closing() as conn:
            row = conn.execute("SELECT health, xp FROM player WHERE id = 1").fetchone()
            return int(row["health"]), int(row["xp"])

    def _set_attitude(self, attitude):
        from app import db

        with db.connect().closing() as conn:
            conn.execute("UPDATE npcs SET attitude = ? WHERE code = 'ZA'", (attitude,))
            conn.commit()

    def _apply(self, prose, line, player, **extra):
        from app import world

        turn = {"narration": prose, "player": dict(player), "inventory_changes": [],
                "self_check": {"passed": True, "issues_found": [], "corrections_made": []}, "turn_summary": "test"}
        turn.update(extra)
        notes = Notes()
        with mock.patch("app.turn_ledger.note", notes):
            world.apply_turn(turn, line)
        return turn, notes

    def test_t41_the_declared_blow_takes_no_health_and_earns_no_xp(self):
        health, xp = self._player()
        turn, notes = self._apply(T41_PROSE, T41_LINE, {"health_band": "-moderate", "xp_band": "trivial"})
        self.assertEqual(self._player(), (health, xp))
        voided = notes.named("declared_blow_not_applied")
        self.assertEqual(len(voided), 1)
        self.assertLess(voided[0]["health_delta"], 0)
        self.assertEqual(voided[0]["codes"], ["ZA"])
        self.assertIn("xp_dropped", turn.get("_reward_gate") or {})

    def test_t16_a_band_on_the_guards_stab_would_be_voided_too(self):
        health, _xp = self._player()
        _turn, notes = self._apply("The guard's blade passes through you.", T16_LINE, {"health_band": "-large"})
        self.assertEqual(self._player()[0], health)
        voided = notes.named("declared_blow_not_applied")
        self.assertEqual(len(voided), 1)
        self.assertEqual(voided[0]["codes"], [])  # "A guard": no guard here, no one on record

    def test_t50_held_no_band_nothing_applied(self):
        health, xp = self._player()
        self._apply(T50_PROSE, T50_LINE, {})
        self.assertEqual(self._player(), (health, xp))

    def test_a_hostile_on_record_keeps_the_fights_band(self):
        self._set_attitude("hostile")
        health, _xp = self._player()
        _turn, notes = self._apply(T41_PROSE, T41_LINE, {"health_band": "-moderate"})
        self.assertLess(self._player()[0], health)
        self.assertFalse(notes.named("declared_blow_not_applied"))
        self.assertEqual(len(notes.named("declared_blow_hostile_kept")), 1)

    def test_an_engine_authored_injury_still_applies(self):
        # A skill check's own injury (the unskilled mishap, F193) is server-authored: it passes on its own path.
        health, _xp = self._player()
        self._apply(T41_PROSE, T41_LINE, {"health_delta": -2}, _server_authored=["player.health_delta"])
        self.assertEqual(self._player()[0], health - 2)

    def test_a_blow_the_prose_gives_with_no_declared_line_still_hurts(self):
        health, _xp = self._player()
        _turn, notes = self._apply("Bartholomew's cudgel catches you across the shoulder.",
                                   "I shove past Bartholomew toward the door.", {"health_band": "-small"})
        self.assertLess(self._player()[0], health)
        self.assertFalse(notes.named("declared_blow_not_applied"))

    def test_t10_xp_for_the_declared_gift_is_not_earned(self):
        _health, xp = self._player()
        turn, notes = self._apply(T10_PROSE, T10_LINE, {"xp_band": "large"},
                                  inventory_changes=[{"name": "sword", "quantity_delta": 1}])
        self.assertEqual(self._player()[1], xp)
        self.assertIn("xp_dropped", turn.get("_reward_gate") or {})
        self.assertEqual([r["declared"] for r in notes.named("xp_not_earned")], [["find"]])

    def test_a_quest_payout_still_pays(self):
        _health, xp = self._player()
        self._apply(T10_PROSE, T10_LINE, {"xp_delta": 20}, _server_authored=["player.xp_delta"])
        self.assertEqual(self._player()[1], xp + 20)

    def test_an_engine_check_still_earns_on_a_declared_line(self):
        from app import world

        result = {"skill_checks": [{"natural": 14, "skill": {"category": "combat"}}]}
        outcomes = world._turn_outcomes(None, result, player_input="The guard lunges at me and I stab him")
        self.assertIn("check", outcomes)


if __name__ == "__main__":
    unittest.main()
