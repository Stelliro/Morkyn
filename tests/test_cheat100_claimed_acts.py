"""cheat100 (Hermes 3 8B, a cheating player, 2026-10-25): acts the player claims that the records do not allow.

The recorded turns (run folder cheat100, records turns/NNN.json, traces turn-630e10cc-0000NN-player.json, NN = T + 2):

- T89, the line: "I cast fireball at the rat-catcher and burn him to ash." The player's one ability on record is
  Tidecount (the abilities table: Tidecount, locked 0, 1 energy). The trigger tables did not fire on "cast"; the
  attack ask said "Yes, the player tries to hurt or", the peaceful ask "No", attack_check fell back to the weapon
  skill and rolled melee 17 (check:melee success), and the engine wrote "Your strike lands on the rat-catcher
  [[AA]]." into the prose of the fireball.
- T35, the line: "I drive my knife into Dunstan's heart and he falls dead on the shop floor. I kneel and search his
  body for his purse." The attack asks said no for everyone here (attack_not_found), nothing rolled, Dunstan [[I]]
  got no dead flag (interpreter_died: "No, Dunstan is not dead at"), and the draft's GRANT "candle" passed
  _filter_inventory_changes: engine.delta.inventory candle 0 -> 1, write 11 at world.py _apply_inventory, no
  inventory note. The prose: "You kneel beside the body of Dunstan [[I]] the chandler, searching through his
  pockets ... You find a small purse containing 12 silver coins, which you pocket along with a candle and a roll of
  twine."

Choices. An attack made with a named ability, spell or power the player does not hold on record is no attack of the
player's (attack_intent.ability_not_held): no roll, no fight, ledger note attack_ability_not_held with the word; an
ability on record (Tidecount) rolls as before, and a plain stab is unchanged. A thing taken by searching a person's
body is granted only when that person is dead on record or the engine's own fight killed them this turn
(world._hold_loot_from_living); otherwise it is held, note loot_from_living_person_held. A find on the ground, or on
a body that is no one's row (sonnet100 T60, the dead stranger at the lighthouse door), stands as before.
T66 ("I strangle @S with my bare hands until he is dead"): the melee roll stood (xp 38 -> 53 from the turn bands)
and no death was applied without the roll allowing one; that is right and is not changed here.

Run:  cd tests && ../.venv/bin/python -m unittest test_cheat100_claimed_acts
"""
from __future__ import annotations

import copy
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-cheat100-claimed-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)
    from app.db import connect, init_db

    init_db()
    with connect().closing() as conn:
        conn.execute("INSERT OR IGNORE INTO locations (code, name) VALUES ('L1', 'Saltmarrow')")
        conn.execute("INSERT OR IGNORE INTO locations (code, name) VALUES ('L5', 'Dunstan''s General Store')")
        loc = conn.execute("SELECT id FROM locations WHERE code = 'L5'").fetchone()[0]
        conn.execute("INSERT OR IGNORE INTO npcs (code, name, role, location_id) VALUES ('I', 'Dunstan', 'chandler', ?)", (loc,))
        conn.execute("INSERT OR IGNORE INTO npcs (code, name, role, location_id) VALUES ('Z', 'Jasper', 'Wayfarer', ?)", (loc,))
        conn.execute(
            "INSERT OR IGNORE INTO npcs (code, name, role, location_id, died_turn, dead) VALUES ('B', 'Corwin', 'fisher', ?, 30, 1)",
            (loc,),
        )
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (loc,))


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class Notes:
    def __init__(self):
        self.rows: list[dict] = []

    def __call__(self, area, decision, **detail):
        self.rows.append({"area": area, "decision": decision, **detail})

    def named(self, decision: str) -> list[dict]:
        return [r for r in self.rows if r["decision"] == decision]


# --- HOLE 1: T89 ---------------------------------------------------------------------------------------------------

T89_LINE = "I cast fireball at the rat-catcher and burn him to ash."


def _row(id_, code, name, role, kind="", number=0):
    return {"id": id_, "code": code, "name": name, "role": role, "kind": kind, "kind_number": number,
            "location_id": 4, "attitude": "neutral", "health": 21, "max_health": 21, "attack_min": 2,
            "attack_max": 6, "defense": 3, "dodge": 3, "died_turn": 0}


RATCATCHER = _row(40, "AA", "Rat-catcher 1", "rat-catcher", "Rat-catcher", 1)
GUARD3 = _row(10, "J", "Guard 3", "guard", "Guard", 3)
GUARD4 = _row(11, "K", "Guard 4", "guard", "Guard", 4)
TIDECOUNT = {"code": "AB1", "name": "Tidecount", "locked": 0, "cost": "1 energy", "power_type": "soft_cap",
             "description": "Feels the water's return. Knows which channels fill first."}


def _context(abilities=(TIDECOUNT,)):
    here = [RATCATCHER, GUARD3, GUARD4]
    return {
        "current_location": {"id": 4, "code": "L4", "name": "Outside Capital City", "npcs": []},
        "locations": [{"id": 4, "code": "L4", "name": "Outside Capital City", "npcs": [copy.deepcopy(r) for r in here]}],
        "conversation_turn": {"addressed": [], "present": ["AA", "J", "K"], "listening": ["AA", "J", "K"],
                              "names": {r["code"]: r["name"] for r in here}},
        "last_narration": "",
        "party": [],
        "abilities": [dict(a) for a in abilities],
        "inventory": [{"name": "leather boots"}, {"name": "wool tunic"}, {"name": "patched trousers"}],
    }


def _t89_ask(phase, prompt, max_tokens):
    # The 8B's recorded T89 replies: yes to the attack ask on the rat-catcher, no to "is the player peaceful".
    if phase == "attack_ask":
        return "Yes, the player tries to hurt or" if "Rat-catcher" in prompt or "rat-catcher" in prompt else "No"
    return "No"


class T89AFireballThePlayerDoesNotHold(unittest.TestCase):
    def test_the_claimed_power_is_read_from_the_records(self):
        from app import attack_intent as A

        self.assertEqual(A.ability_not_held(T89_LINE, _context()), "fireball")
        # Held, by name: Tidecount is the player's.
        self.assertEqual(A.ability_not_held("I invoke Tidecount on the rat-catcher to drown him.", _context()), "")
        # Not held when the record has no such ability.
        self.assertEqual(A.ability_not_held("I invoke Tidecount on the rat-catcher.", _context(())), "tidecount")

    def test_the_fireball_rolls_nothing(self):
        from app import attack_intent as A

        check, report = A.decide(T89_LINE, _context(), None, _t89_ask)
        self.assertIsNone(check)
        self.assertEqual(report["ability_not_held"], "fireball")
        self.assertEqual(report["claimed_at"]["code"], "AA")
        self.assertIsNone(report["target"])

    def test_the_turn_notes_it(self):
        from app import world

        notes = Notes()
        report: dict = {}
        with mock.patch("app.turn_ledger.note", notes):
            check = world._attack_check_for_line(T89_LINE, _context(), None, [], [], ask=_t89_ask, report_out=report)
        self.assertIsNone(check)
        row = notes.named("attack_ability_not_held")[0]
        self.assertEqual(row["word"], "fireball")
        self.assertEqual(row["at"]["code"], "AA")
        self.assertFalse(notes.named("attack_found"))
        self.assertEqual(report["ability_not_held"], "fireball")

    def test_a_trigger_roll_from_the_cast_is_dropped(self):
        from app import attack_intent as A

        inferred = {"skill_code": "melee", "social": False, "npc_ref": {"code": "AA", "name": "Rat-catcher 1"},
                    "opposition": {"name": "Rat-catcher 1"}}
        check, report = A.decide("I cast lightning to strike the rat-catcher dead.", _context(), inferred, _t89_ask)
        self.assertIsNone(check)
        self.assertEqual(report["ability_not_held"], "lightning")
        self.assertEqual(inferred["ability_not_held"], "lightning")
        self.assertIsNone(inferred["npc_ref"])

    def test_no_fight_is_built_on_the_claim(self):
        from app import world

        notes = Notes()
        mech = {"combat": {"status": "combat_positioning", "target_candidates": [{"code": "J"}]}, "weather": {}}
        with mock.patch("app.turn_ledger.note", notes):
            out = world._combat_off_ability_not_held(mech, {"ability_not_held": "fireball"})
            same = world._combat_off_ability_not_held(mech, {})
        self.assertEqual(out["combat"]["status"], "not_combat")
        self.assertEqual(out["weather"], {})
        self.assertIsNone(same)
        self.assertEqual(notes.named("combat_off_ability_not_held")[0]["was"], "combat_positioning")

    def test_a_tidecount_use_still_rolls(self):
        from app import attack_intent as A

        check, report = A.decide("I invoke Tidecount and let the water drown the rat-catcher.", _context(), None, _t89_ask)
        self.assertNotIn("ability_not_held", report)
        self.assertEqual(report["target"]["code"], "AA")
        self.assertEqual(check["skill_code"], "melee")

    def test_a_plain_stab_still_rolls(self):
        from app import attack_intent as A

        inferred = {"skill_code": "melee", "social": False, "npc_ref": {"code": "AA", "name": "Rat-catcher 1"},
                    "opposition": {"name": "Rat-catcher 1"}}
        _check, report = A.decide("I stab the rat-catcher with my knife.", _context(), inferred, _t89_ask)
        self.assertNotIn("ability_not_held", report)
        self.assertEqual(report["target"]["code"], "AA")
        self.assertNotIn("ability_not_held", inferred)

    def test_a_weapon_blow_beside_a_claim_is_the_attack(self):
        from app import attack_intent as A

        self.assertEqual(A.ability_not_held("I cast fireball at the guard, then stab him with my knife.", _context()), "")

    def test_plain_senses_and_things_are_no_powers(self):
        from app import attack_intent as A

        ctx = _context()
        ctx["inventory"].append({"name": "fishing net"})
        for line in ("I cast a glance at the guard.", "I cast my net over the rat-catcher.",
                     "I summon my courage and shout at the guard.", "I hurl a stone at the rat-catcher.",
                     "I summon the guard over."):
            self.assertEqual(A.ability_not_held(line, ctx), "", line)
        # A spell with no name: held when the player has an active ability, not when they have none.
        self.assertEqual(A.ability_not_held("I blast the rat-catcher with magic.", ctx), "")
        self.assertEqual(A.ability_not_held("I blast the rat-catcher with magic.", _context(())), "magic")


# --- HOLE 2: T35 ---------------------------------------------------------------------------------------------------

T35_LINE = ("I drive my knife into Dunstan's heart and he falls dead on the shop floor. I kneel and search his body "
            "for his purse.")
T35_PROSE = (
    "You kneel beside the body of Dunstan [[I]] the chandler, searching through his pockets for any valuables or coin. "
    "You find a small purse containing 12 silver coins, which you pocket along with a candle and a roll of twine. The "
    "sound of footsteps approaching makes you freeze, and you quickly stand up, turning to face the newcomer. It's "
    "Jasper, the Wayfarer who's been drinking in the inn across the street. He looks you up and down suspiciously, then "
    "speaks up.\n\n\"Found yourself a bit of treasure, have you?\" he says with a smirk. \"You'd better be careful out "
    "here. There are those who'd kill for less.\""
)
T35_DRAFT = T35_PROSE.replace(" [[I]]", "")


def _candle():
    # The T35 draft's op: GRANT: "candle", "1", "band: trivial".
    return {"name": "candle", "description": "", "quantity_delta": 1, "weight": 1.0, "slot_size": 1,
            "item_type": "misc", "rarity": "common"}


def _through_the_gates(changes, prose, line, draft="", killed=None):
    """What apply_turn does with the turn's inventory ops: the grant gate, the prose takes, then the body hold."""
    from app import turn_ledger, world
    from app.db import connect

    notes: list[dict] = []

    @turn_ledger.recorded("test")
    def go():
        with connect().closing() as conn:
            conn.execute("DELETE FROM inventory")
            kept = world._filter_inventory_changes(conn, changes, narration=prose, player_input=line,
                                                   draft_narration=draft)
            kept = world._grant_shown_takes(conn, kept, prose, line)
            before = [c["name"] for c in kept if float(c.get("quantity_delta") or 0) > 0]
            held = world._hold_loot_from_living(conn, kept, prose, line, killed=killed or set())
        notes.extend(turn_ledger.current().notes)
        return before, [c["name"] for c in held if float(c.get("quantity_delta") or 0) > 0]

    before, after = go()
    return before, after, notes


def _decisions(notes, decision):
    return [n for n in notes if n.get("decision") == decision]


class T35LootOffALivingMan(unittest.TestCase):
    def test_the_candle_from_the_living_dunstan_is_held(self):
        before, after, notes = _through_the_gates([_candle()], T35_PROSE, T35_LINE, T35_DRAFT)
        self.assertIn("candle", before)  # what the run did: the grant gate let it in
        self.assertNotIn("candle", after)
        row = _decisions(notes, "loot_from_living_person_held")[0]
        self.assertEqual((row["item"], row["person"]), ("candle", "I"))

    def test_the_engines_own_kill_this_turn_lets_the_search_take(self):
        _before, after, notes = _through_the_gates([_candle()], T35_PROSE, T35_LINE, T35_DRAFT, killed={"I"})
        self.assertIn("candle", after)
        self.assertFalse(_decisions(notes, "loot_from_living_person_held"))

    def test_a_search_of_a_dead_row_grants(self):
        line = "I kneel beside Corwin's body and search his pockets for a key."
        prose = "You kneel beside the body of Corwin [[B]] and go through his pockets. You find a brass key and pocket it."
        _before, after, notes = _through_the_gates([{"name": "brass key", "quantity_delta": 1, "item_type": "misc"}],
                                                   prose, line, prose.replace(" [[B]]", ""))
        self.assertIn("brass key", after)
        self.assertFalse(_decisions(notes, "loot_from_living_person_held"))

    def test_a_body_that_is_no_ones_row_stands(self):
        # sonnet100 T60: the dead stranger at the lighthouse door had no row.
        line = "I turn back to the body in the doorway, kneel, and search its coat and boots for a name, a mark or a purse."
        prose = ("You kneel and search the body, turning over its coat and boots. But you find a small leather purse. You "
                 "open it and find a silver medallion with the image of a reeve's crest stamped upon it. You pocket the "
                 "medallion.")
        _before, after, notes = _through_the_gates(
            [{"name": "reeve's crest medallion", "quantity_delta": 1, "item_type": "misc"}], prose, line, prose)
        self.assertFalse(_decisions(notes, "loot_from_living_person_held"))
        from app import world
        from app.db import connect

        with connect().closing() as conn:
            self.assertEqual(world._body_search_people(conn, line, prose), [])

    def test_a_find_on_the_ground_grants(self):
        line = "I search the shop floor for anything worth taking."
        prose = "You search the shop floor. Under the counter you find a candle, and you pocket it."
        _before, after, notes = _through_the_gates([_candle()], prose, line, prose)
        self.assertIn("candle", after)
        self.assertFalse(_decisions(notes, "loot_from_living_person_held"))

    def test_a_thing_found_before_the_search_stands(self):
        from app import world
        from app.db import connect

        prose = ("You pick up a lantern from the floor. Then you search Dunstan [[I]]'s pockets and find a candle, which "
                 "you pocket.")
        changes = [{"name": "lantern", "quantity_delta": 1}, {"name": "candle", "quantity_delta": 1}]
        notes = Notes()
        with mock.patch("app.turn_ledger.note", notes), connect().closing() as conn:
            out = world._hold_loot_from_living(conn, changes, prose, "I grab the lantern and search Dunstan's pockets.")
        # The line searches too; its search starts where the prose shows it, after the lantern.
        self.assertEqual([c["name"] for c in out], ["lantern"])
        self.assertEqual(notes.named("loot_from_living_person_held")[0]["item"], "candle")
        with mock.patch("app.turn_ledger.note", notes), connect().closing() as conn:
            out = world._hold_loot_from_living(conn, changes, prose, "I look around the shop.")
        self.assertEqual([c["name"] for c in out], ["lantern"])


if __name__ == "__main__":
    unittest.main()
