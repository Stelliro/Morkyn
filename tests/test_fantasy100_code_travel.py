"""fantasy100 (Hermes 3 8B, four Sonnet players, Thornhallow, 2026-10-26): F210, code travel noted
as repaired but not written, and the F207 partial (T63).

The notes of T84, T85, T86 ("I accept the work on the slip, head to #L2, and ask the barkeep @B what
the pay is.", "I walk into The Shears and Wheel at #L2 ...", "I go to #L2.") read player_code_travel
L2 and where_ended_disagrees status repaired, yet the save stayed in Thornhallow. The ledger says
why: the venue gate (world.gate_venue_move, in _apply_player) wrote "The Shears and Wheel is closed
now (11:00-02:00)" each turn; it was 08:09. The engine knew before the draft (movement_contract
.closed_now, venues_here hours) but the packet dropped both, and facts_to_keep only said the hours
of plotted-town places, so the prose sat the player in a bustling taproom three turns running.
Fixed by shipping the fact the model was missing: facts_to_keep now says a closed venue here
outside a plotted town, in the sentence the town path already uses. The gate keeps the save.

T50 "I bid Gisela goodnight and head back to #L3, the Chandlers' Guild hall, to pay part of
Hesper's debt." from Ruins (L8): the hall stands in Thornhallow, so the venue gate ended the journey
there ("is entered from Thornhallow"). The prose ends "a good mile or more to go". Kept: the move
is the player's own (they set off and arrive in the village of the hall); going in costs the next
turn, as T51 "I walk to #L3 ..." then did. Only the journal said "moved the player to the
Chandlers' Guild hall"; it now says where the journey ended.

T63 "I leave the road and climb into the Greywold hills toward #L4, the old ruins, looking for any
beast tracks." read "the old ruins" as the place Ruins (L8), so the typed #L4 (Greywold Ruins) was
never bound and the save landed in Ruins. One typed code beside another place's name now wins.

T98 (L3 -> L1 by "tell @A in #L1") and T51 (Thornhallow -> the guild hall) stay correct.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-fantasy100-codetravel-"))
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


T84_LINE = "I accept the work on the slip, head to #L2, and ask the barkeep @B what the pay is."
T84_PROSE = (
    "The tavern is bustling with activity this early in the day: patrons huddle around tables, deep in conversation "
    "while two servers weave between them, deftly balancing trays of tankards and platters.\n\n"
    "A tapster catches your eye from across the room - Nicol Skinner, as he's called, a man you've seen about town "
    "before. He's wiping down mugs with a rag, his gaze flicking over to you with a hint of curiosity."
)
T50_LINE = "I bid Gisela goodnight and head back to #L3, the Chandlers' Guild hall, to pay part of Hesper's debt."
T50_PROSE = (
    "You bid Gisela [[N]] good evening and make your polite excuses to leave. There's no need for a long goodbye - "
    "you have business that calls, after all.\n\n"
    "With a final nod to the woodcutter, you turn your steps towards the distant lights of the Chandlers' Guild hall "
    "[[L3]]: the Chandlers' Guildhall. The cobbled path crunches softly underfoot as you walk, your soft-soled boots "
    "offering quiet purchase on the stones.\n\n"
    "The moon is waning gibbous and nearly full; by its light, you pick out the familiar silhouette of the Guildhall "
    "against the starry sky. It's a good mile or more to go - the Chandlers' guild does not look kindly upon those "
    "who arrive at their door with empty hands."
)
T63_LINE = "I leave the road and climb into the Greywold hills toward #L4, the old ruins, looking for any beast tracks."
T63_PROSE = (
    "You leave the old King's Road [[L9]] behind and climb into the Greywold hills toward Greywold Ruins [[L4]], the "
    "ancient ruins. The path winds between craggy outcroppings and stands of leafless trees. You keep a watchful eye "
    "out for any signs of beast tracks or disturbed earth.\n\n"
    "As you crest a small rise, you catch sight of something glinting in the moonlight off to your left."
)
T51_LINE = "I walk to #L3, the Chandlers' Guild hall, to speak about Hesper's debt."
T51_PROSE = (
    "Entering the guild hall, you find yourself in an impressive foyer with a high vaulted ceiling supported by ornate "
    "pillars. A wide staircase sweeps down from the second floor to your left, leading to offices and meeting rooms "
    "above.\n\nYou knock politely and wait for a response."
)
T98_LINE = "I thank @Q Ermengarde, then tell @A in #L1 that I will sell him the dried meat tomorrow."
T98_PROSE = (
    "Ermengarde [[Q]] watches with interest. There's a scent of roasting meat that makes your stomach grumble. "
    "Roger [[A]] nods curtly in acknowledgement of your promise before returning to his work, a large knife in hand "
    "as he begins jointing a chicken."
)


def _world(here: str = "Thornhallow", minute: int = 489) -> dict[str, int]:
    """The fantasy100 places as recorded: L1 Thornhallow (a village), L2 The Shears and Wheel (tavern, 11:00-02:00)
    and L3 the Chandlers' Guild hall (guild hall, 08:00-19:00) and L4 Greywold Ruins in it, L5 Deeper Into Ruins,
    L6 Outside Thornhallow, L8 Ruins (under L6), L9 old King's Road; the player at ``here``, the clock at ``minute``."""
    from app import world
    from app.db import connect, init_db

    init_db()
    world.start_playthrough({"player_name": "Wren Ashcombe", "start_location": "Thornhallow",
                             "special_ability_origin": "none"})
    with connect().closing() as conn:
        town = int(conn.execute("SELECT id FROM locations WHERE name = 'Thornhallow'").fetchone()[0])
        conn.execute("UPDATE locations SET code = 'L1', settlement_size = 'village' WHERE id = ?", (town,))
        conn.execute("DELETE FROM locations WHERE id != ?", (town,))
        ids = {"Thornhallow": town}
        for code, name, parent, kind, opens, closes in (
            ("L2", "The Shears and Wheel", "Thornhallow", "tavern", 660, 120),
            ("L3", "the Chandlers' Guild hall", "Thornhallow", "guild_hall", 480, 1140),
            ("L4", "Greywold Ruins", "Thornhallow", "", -1, -1),
            ("L5", "Deeper Into Ruins", "", "", -1, -1),
            ("L6", "Outside Thornhallow", "", "", -1, -1),
            ("L8", "Ruins", "Outside Thornhallow", "", -1, -1),
            ("L9", "old King's Road", "", "", -1, -1),
        ):
            cur = conn.execute(
                "INSERT INTO locations (code, name, summary, visit_count, parent_id, kind, open_minute, close_minute) "
                "VALUES (?, ?, '', 1, ?, ?, ?, ?)",
                (code, name, ids.get(parent, 0), kind, opens, closes),
            )
            ids[name] = int(cur.lastrowid)
        conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (ids[here],))
        for code, name, role, at in (
            ("A", "Roger", "kitchen hand", "Thornhallow"),
            ("B", "Arnulf Bramley", "barkeep", "The Shears and Wheel"),
            ("N", "Gisela", "woodcutter", here),
            ("Q", "Ermengarde", "guild clerk", "the Chandlers' Guild hall"),
        ):
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES (?, ?, ?, ?)", (code, ids[at], name, role))
        world._pacing_set(conn, "world_minute", minute)
        conn.commit()
    return ids


@contextlib.contextmanager
def _notes():
    from app import turn_ledger

    ledger = turn_ledger.Ledger("test")
    token = turn_ledger._CURRENT.set(ledger)
    try:
        yield ledger
    finally:
        turn_ledger._CURRENT.reset(token)


def _here() -> str:
    from app.db import connect

    with connect().closing() as conn:
        return str(conn.execute("SELECT l.name FROM player p JOIN locations l ON l.id = p.current_location_id "
                                "WHERE p.id = 1").fetchone()[0])


def _journal(kind: str) -> list[str]:
    from app.db import connect

    with connect().closing() as conn:
        return [str(r[0]) for r in conn.execute("SELECT content FROM journal WHERE kind = ? ORDER BY id", (kind,))]


def _turn(result: dict, line: str, *, going: str = "Yes", letter: str | None = None, confirm: str = "No."):
    """The real order of play_turn: the reference asks, the where-ended ask, then apply_turn. Returns the report."""
    from app import entity_kinds, where_ended, world
    from app.db import connect

    asks: list[str] = []

    def kind_ask(system, user, *, trace=None, usage=None, phase="", max_tokens=0):
        asks.append(user)
        return going

    prev_kind = entity_kinds.set_kind_ask(kind_ask)
    prev_where = where_ended.set_ask((lambda s, u: letter if s == "Answer with one letter." else confirm)
                                     if letter else None)
    try:
        entity_kinds.settle_place_reference(result, line)
        if letter:
            with connect().closing() as conn:
                where_ended.ask_where(conn, result, line, result["narration"])
        state = world.apply_turn(result, line)
    finally:
        entity_kinds.set_kind_ask(prev_kind)
        where_ended.set_ask(prev_where)
    result["_asks"] = asks
    return (state or {}).get("movement") or {}


def _facts(line: str) -> list[str]:
    from app import world
    from app.turn_dsl import facts_to_keep

    return facts_to_keep(world.build_prompt_context(world.get_state(), line))


def _decisions(ledger, name: str) -> list[dict]:
    return [n for n in ledger.notes if n.get("decision") == name]


class AClosedVenueIsAFactTheNarratorGets(unittest.TestCase):
    def test_t84_the_closed_tavern_is_in_facts_to_keep_before_the_draft(self):
        # Recorded packet: facts_to_keep ["You are in Thornhallow [[L1]].", "It is morning, 08:09."] only,
        # while movement_contract.closed_now held "The Shears and Wheel".
        _world(minute=489)
        facts = _facts(T84_LINE)
        self.assertIn("The Shears and Wheel is closed; its hours are 11:00-02:00.", facts)
        self.assertFalse([f for f in facts if "Guild hall" in f], "an open place needs no fact")
        self.assertTrue(facts[0].startswith("You are in Thornhallow"), facts)

    def test_open_at_noon_no_closed_fact(self):
        _world(minute=720)
        self.assertFalse([f for f in _facts(T84_LINE) if "closed" in f])

    def test_t84_the_gate_still_keeps_the_save_and_the_report_says_refused(self):
        # Recorded draft: MOVE The Shears and Wheel, prose inside the taproom; where-ended "A) still in" / "Yes".
        _world(minute=489)
        result = {"narration": T84_PROSE, "player": {"move_to_location": "The Shears and Wheel"}}
        with _notes() as ledger:
            report = _turn(result, T84_LINE, letter="A) still in", confirm="Yes, you are")
        self.assertEqual(_decisions(ledger, "player_code_travel")[0]["code"], "L2")
        self.assertEqual(_here(), "Thornhallow")
        self.assertEqual(report.get("refused"), "venue_closed", report)
        self.assertTrue(any("closed now (11:00-02:00)" in j for j in _journal("venue_closed")))

    def test_t84_after_opening_the_same_line_goes_in(self):
        _world(minute=700)
        result = {"narration": T84_PROSE, "player": {}}
        with _notes():
            report = _turn(result, T84_LINE, letter="A) still in", confirm="Yes, you are")
        self.assertEqual(_here(), "The Shears and Wheel")
        self.assertEqual(report.get("rule"), "player_code", report)


class AJourneyToAVenueEndsAtItsDoorPlace(unittest.TestCase):
    def test_t50_from_the_ruins_the_hall_is_reached_in_thornhallow_and_the_journal_says_so(self):
        # Recorded: from Ruins (L8) at 00:02; where-ended "C) outside" / "No."; the save went to L1.
        _world(here="Ruins", minute=2)
        result = {"narration": T50_PROSE, "player": {}}
        with _notes() as ledger:
            report = _turn(result, T50_LINE, letter="C) outside", confirm="No.")
        self.assertEqual(_decisions(ledger, "player_code_travel")[0]["code"], "L3")
        self.assertEqual(_here(), "Thornhallow")
        self.assertEqual(report.get("landed"), "Thornhallow", report)
        systems = [j for j in _journal("system") if "player_code" in j]
        self.assertTrue(systems, _journal("system"))
        self.assertIn("toward the Chandlers' Guild hall", systems[-1])
        self.assertIn("entered from Thornhallow", systems[-1])
        self.assertNotIn("moved the player to the Chandlers' Guild hall", systems[-1])

    def test_t51_standing_in_thornhallow_the_same_hall_is_entered(self):
        # Recorded: T51 went Thornhallow -> the guild hall (still correct). Clock set inside its hours.
        _world(here="Thornhallow", minute=600)
        with _notes() as ledger:
            report = _turn({"narration": T51_PROSE, "player": {}}, T51_LINE, letter="A) still in", confirm="Yes, you are")
        self.assertEqual(_here(), "the Chandlers' Guild hall")
        self.assertEqual(report.get("rule"), "player_code", report)
        self.assertEqual(_decisions(ledger, "place_bound_by_reference")[0]["how"], "typed_and_named")


class TheTypedCodeBeatsAnotherPlacesWord(unittest.TestCase):
    def test_t63_toward_l4_the_old_ruins_goes_to_greywold_ruins_not_ruins(self):
        # Recorded: no binding; where_ended_disagrees destination Ruins; the save went L9 -> L8 Ruins.
        _world(here="old King's Road", minute=98)
        with _notes() as ledger:
            report = _turn({"narration": T63_PROSE, "player": {}}, T63_LINE, letter="B) outside", confirm="No.")
        bound = _decisions(ledger, "place_bound_by_reference")
        self.assertEqual((bound[0]["code"], bound[0]["how"]), ("L4", "typed_over_named"), ledger.notes)
        self.assertEqual(report.get("rule"), "player_code", report)
        self.assertEqual(_here(), "Greywold Ruins")

    def test_the_named_place_still_wins_when_the_typed_code_is_its_own_or_the_origin(self):
        from app import entity_kinds
        from app.db import connect

        _world(here="old King's Road")
        with connect().closing() as conn:
            rows = conn.execute("SELECT id, code, name, parent_id, kind FROM locations ORDER BY id").fetchall()
        found = entity_kinds._typed_code_travel(rows, "I walk to #L8, the Ruins.", "old King's Road")
        self.assertEqual((str(found[0]["code"]), found[1]), ("L8", "typed_and_named"))
        # The code typed only as where the player comes from binds nothing.
        self.assertIsNone(entity_kinds._typed_code_travel(rows, "I leave #L4 and walk to the Ruins.", "old King's Road"))
        # Two typed codes beside another name: not decided here.
        self.assertIsNone(entity_kinds._typed_code_travel(
            rows, "I walk past #L5 and #L4 to the Ruins.", "old King's Road"))


class StillCorrect(unittest.TestCase):
    def test_t98_from_the_hall_tell_roger_in_l1_moves_to_thornhallow(self):
        # Recorded: bound L1 by the going ask ("Yes"), where-ended "A) still in" / "Yes"; save L3 -> L1.
        _world(here="the Chandlers' Guild hall", minute=624)
        with _notes():
            report = _turn({"narration": T98_PROSE, "player": {}}, T98_LINE, letter="A) still in", confirm="Yes, you are")
        self.assertEqual(_here(), "Thornhallow")
        self.assertEqual(report.get("rule"), "player_code", report)


if __name__ == "__main__":
    unittest.main()
