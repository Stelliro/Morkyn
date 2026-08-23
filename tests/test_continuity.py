"""
Regression tests for turn-to-turn continuity: movement, narrative voice, NPC names.

All three cover the same failure class — state the model is supposed to maintain
but silently drops on a 7B. Measured on a 30-turn qwen2.5:7b-instruct run:
zero MOVE ops across eight travel turns, 11 of 30 narrations in third person,
and an NPC recorded with the name "Woman".

Run:  python tests/test_continuity.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-continuity-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app.db import connect, init_db  # noqa: E402
from app.world import (  # noqa: E402
    _upsert_location,
    check_narrative_voice,
    invent_person_name,
    is_generic_person_label,
    is_plausible_person_name,
    movement_contract,
    name_seed,
    narrative_voice_contract,
    player_pronouns,
    resolve_movement,
    travel_intent,
)

# Isolation is a correctness requirement, not a convenience: these tests write
# locations, NPCs and rolls. Assert it took hold rather than trusting import
# order -- when the runtime paths were frozen at first import, running the whole
# suite sent these fixtures into the player's real data/world.db.
def _assert_isolated() -> None:
    from app.db import db_path
    import app.world as _world

    for label, value in (
        ("AI_RPG_DB", db_path()),
        ("AI_RPG_SOURCE_INDEX", _world.source_index_dir()),
        ("AI_RPG_HISTORY_SUMMARY", _world.history_summary_path()),
    ):
        if not str(value).startswith(str(_TMP)):
            raise AssertionError(
                f"test isolation failed: {label} resolves to {value!r}, "
                f"outside the temp dir {_TMP!r}"
            )


def setUpModule() -> None:
    """Re-pin this module's runtime paths before its tests run.

    unittest imports every test module up front, and the paths live in
    process-global environment variables -- so without this the module imported
    last owns the database while everyone else's tests execute against it.
    """
    os.environ.update(_ENV)
    _assert_isolated()


init_db()

with connect() as _conn:
    _upsert_location(_conn, "Mosswake Gate", "The town gate.")
    _upsert_location(_conn, "Redmill Ford", "A river crossing east of town.")
    _conn.execute(
        "UPDATE player SET current_location_id = (SELECT id FROM locations WHERE name = 'Mosswake Gate') WHERE id = 1"
    )


def _move(result, player_input, *, intent="travel", narration=""):
    with connect() as conn:
        return resolve_movement(conn, result, player_input, intent=intent, narration=narration)


class TestGenericNpcNames(unittest.TestCase):
    """A description is not a name. Observed: an NPC stored as "Woman", code C."""

    def test_rejects_bare_and_modified_descriptions(self):
        for bad in (
            "Woman", "Man", "the woman", "Old Man", "Hooded Figure", "A Tall Woman",
            "Guard", "Stranger", "Cloaked Stranger", "young guard", "Mysterious Figure",
            "The Old Guard", "nameless woman", "someone", "Female", "Local", "Merchant",
        ):
            with self.subTest(name=bad):
                self.assertTrue(is_generic_person_label(bad))
                self.assertFalse(is_plausible_person_name(bad))

    def test_keeps_real_names_even_with_descriptive_modifiers(self):
        for good in (
            "Aria", "Thornrow", "Jetlane", "Captain Vesk", "Old Mara", "Guard Aria",
            "Mara Thornrow", "Ser Aldric", "Mother Cinder", "Grey Wolf", "Dockhand Kesh",
        ):
            with self.subTest(name=good):
                self.assertFalse(is_generic_person_label(good))
                self.assertTrue(is_plausible_person_name(good))

    def test_replacement_name_is_itself_acceptable(self):
        """The fallback must not land back in the reject set — that would loop."""
        for seed in range(60):
            name = invent_person_name(seed=seed)
            self.assertTrue(is_plausible_person_name(name), name)

    def test_replacement_seed_is_stable_across_processes(self):
        """
        Regression: the seed used to come from Python's hash(), which is
        randomized per process — the same corrupt save renamed the same NPC to
        a different person on every reload.
        """
        code = (
            "import sys; sys.path.insert(0, r'%s');"
            "from app.world import name_seed, invent_person_name;"
            "print(name_seed('C', 'Woman', 'hooded'), invent_person_name(seed=name_seed('C', 'Woman', 'hooded')))"
            % ROOT
        )
        outs = set()
        for hash_seed in ("0", "1", "12345"):
            env = {**os.environ, "PYTHONHASHSEED": hash_seed}
            outs.add(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env).stdout.strip())
        self.assertEqual(len(outs), 1, f"seed drifted across processes: {outs}")


class TestTravelIntent(unittest.TestCase):
    def test_inflected_verbs_are_recognised(self):
        """"keep walking east" scored zero for travel and fell through to `general`."""
        for text in (
            "I keep walking east, watching the treeline",
            "I am going to the market",
            "I ran back to the inn",
            "I head for the east road out of town",
            "I follow the road north toward the next settlement",
        ):
            with self.subTest(text=text):
                self.assertTrue(travel_intent(text))

    def test_non_travel_actions_stay_non_travel(self):
        for text in (
            "I ask the merchant about taxes",
            "I attack the bandit with my sword",
            "I search the crates for anything useful",
            "I equip the leather armour",
            "I buy three loaves of bread",
            "I sold my dagger to the smith",
        ):
            with self.subTest(text=text):
                self.assertFalse(travel_intent(text))

    def test_secondary_travel_counts(self):
        """Ties break in favour of investigation, so travel must count as secondary too."""
        from app.world import _turn_intent

        text = "I keep walking east, watching the treeline for movement."
        primary, secondary = _turn_intent(text)
        self.assertNotEqual(primary, "travel")
        self.assertIn("travel", secondary)
        self.assertTrue(travel_intent(text))


class TestMovementRepair(unittest.TestCase):
    def test_model_supplied_move_is_left_alone(self):
        result = {"player": {"move_to_location_code": "L2"}}
        report = _move(result, "walk east to Redmill Ford")
        self.assertEqual(report["status"], "model")
        self.assertEqual(result["player"]["move_to_location_code"], "L2")

    def test_non_travel_turn_never_moves_the_player(self):
        result = {"player": {}}
        report = _move(result, "I ask the guard about taxes", intent="conversation")
        self.assertEqual(report["status"], "not_travel")
        self.assertEqual(result["player"], {})

    def test_new_place_minted_this_turn_becomes_the_destination(self):
        result = {"player": {}, "locations": [{"name": "Thistledown Camp", "summary": "A camp."}]}
        report = _move(result, "follow the road north until I find somewhere to stop")
        self.assertEqual(report["status"], "repaired")
        self.assertEqual(report["rule"], "new_location")
        self.assertEqual(result["player"]["move_to_location"], "Thistledown Camp")

    def test_place_named_in_player_input_becomes_the_destination(self):
        result = {"player": {}}
        report = _move(result, "head for Redmill Ford")
        self.assertEqual(report["rule"], "player_input")
        self.assertEqual(result["player"]["move_to_location_code"], "L2")

    def test_arrival_language_plus_tagged_code_becomes_the_destination(self):
        result = {"player": {}}
        report = _move(
            result,
            "keep walking east",
            narration="You walk for hours. At dusk you reach Redmill Ford [[L2]], the water loud below.",
        )
        self.assertEqual(report["rule"], "narration_code")
        self.assertEqual(result["player"]["move_to_location_code"], "L2")

    def test_travel_with_no_evidence_stays_put_and_says_so(self):
        result = {"player": {}}
        report = _move(result, "walk around a bit", narration="You pace the yard, thinking.")
        self.assertEqual(report["status"], "unresolved")
        self.assertEqual(result["player"], {})

    def test_arrival_at_the_current_location_is_not_a_move(self):
        """"You reach Mosswake Gate [[L1]] again" must not re-enter the place you are in."""
        result = {"player": {}}
        report = _move(result, "walk back", narration="You reach Mosswake Gate [[L1]] again.")
        self.assertEqual(report["status"], "unresolved")
        self.assertNotIn("move_to_location_code", result["player"])

    def test_unknown_code_in_narration_is_ignored(self):
        result = {"player": {}}
        report = _move(result, "keep walking east", narration="You reach the far shore [[L47]] at dusk.")
        self.assertEqual(report["status"], "unresolved")

    def test_invented_destination_code_is_rejected_not_trusted(self):
        """
        Live 7B failure: with only L1 in the world it wrote `MOVE L2`, inventing
        the next code in sequence. `_find_location_id` resolves an unknown
        L-code back to the current location, so the model looked compliant on
        three straight travel turns while the player never left the gate.
        """
        result = {"player": {"move_to_location_code": "L99"}}
        report = _move(result, "walk around the yard", narration="You circle the muddy yard.")
        self.assertNotEqual(report["status"], "model")
        self.assertIsNone(result["player"]["move_to_location_code"])
        self.assertEqual(report.get("rejected"), "invented_code")

    def test_reusing_a_listed_code_the_prose_never_names_is_flagged(self):
        """
        Live run: the model wrote "You leave Redmill Ford and take the track down
        toward the water", described a river valley, and recorded a move back to
        Mosswake Gate. The prose and the map disagreed. The destination cannot be
        recovered from text that never names it, so this is reported, not guessed.
        """
        result = {"player": {"move_to_location_code": "L2"}}
        report = _move(
            result,
            "I leave and take the track down toward the water",
            narration="The banks grow steeper and the river runs loud below. Wildflowers fringe the mud.",
        )
        self.assertEqual(report["status"], "model")
        self.assertEqual(report.get("prose_mismatch"), "Redmill Ford")
        self.assertEqual(result["player"]["move_to_location_code"], "L2")

    def test_a_destination_the_prose_does_name_is_not_flagged(self):
        result = {"player": {"move_to_location_code": "L2"}}
        report = _move(
            result,
            "head east",
            narration="Hours later you reach Redmill Ford, the water loud below.",
        )
        self.assertEqual(report["status"], "model")
        self.assertNotIn("prose_mismatch", report)

    def test_moving_to_the_current_location_by_name_is_not_a_move(self):
        """Live run: asked to return to a shop, the model wrote MOVE naming the camp
        the player was already standing in. That counted as the model doing its job,
        so no repair rule ever ran and the player never moved."""
        result = {"player": {"move_to_location": "Mosswake Gate"}}
        report = _move(result, "I head back to the ford", intent="travel")
        self.assertNotEqual(report["status"], "model")
        self.assertEqual(report.get("rejected"), "same_place_name")

    def test_moving_to_the_current_location_is_not_a_move(self):
        """Would otherwise inflate visit_count for standing still."""
        result = {"player": {"move_to_location_code": "L1"}}
        report = _move(result, "walk around the yard", narration="You circle the yard.")
        self.assertNotEqual(report["status"], "model")
        self.assertEqual(report.get("rejected"), "same_place_code")

    def test_invented_code_plus_arrival_prose_mints_a_named_place(self):
        """The first journey out of the starting location has no code to move to."""
        result = {"player": {"move_to_location_code": "L91"}}
        report = _move(
            result,
            "I keep walking east, watching the treeline",
            narration=(
                "The road narrows and the hedgerows thin. You walk into a clearing where "
                "the path splits, and the light drops behind the ridge."
            ),
        )
        self.assertEqual(report["status"], "repaired")
        self.assertEqual(report["rule"], "narration_place")
        self.assertTrue(result["player"]["move_to_location"])
        self.assertNotEqual(result["player"]["move_to_location"].lower(), "mosswake gate")

    def test_minting_prefers_a_proper_noun_over_a_terrain_noun(self):
        result = {"player": {"move_to_location_code": "L91"}}
        _move(
            result,
            "I follow the road north",
            narration="You walk into Thistledown Hollow as the mist closes behind you.",
        )
        self.assertEqual(result["player"]["move_to_location"], "Thistledown Hollow")

    def test_minting_never_turns_an_npc_into_a_place(self):
        with connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO npcs (code, location_id, name, role) "
                "VALUES ('Z', (SELECT id FROM locations WHERE name='Mosswake Gate'), 'Thornrow', 'guard')"
            )
        result = {"player": {"move_to_location_code": "L91"}}
        _move(
            result,
            "I keep walking east",
            narration="You leave Thornrow behind and step through into the grove beyond.",
        )
        dest = str(result["player"].get("move_to_location") or "")
        self.assertNotEqual(dest.lower(), "thornrow")
        self.assertTrue(dest)

    def test_no_arrival_language_means_no_minting(self):
        """Deliberating about a journey is not taking one."""
        result = {"player": {"move_to_location_code": "L91"}}
        report = _move(
            result,
            "I check my pack, then head for the east road",
            narration="You pause, considering. You could take the road east, or head back into town.",
        )
        self.assertEqual(report["status"], "unresolved")
        self.assertIsNone(result["player"]["move_to_location_code"])


class TestNarrationPlaceExtraction(unittest.TestCase):
    """
    Naming the place the prose walked into.

    Every candidate must sit behind a destination preposition. Without that
    anchor the extractor named the world after whichever noun the paragraph
    happened to open on ("The road narrows..." -> a location called "Road").
    """

    def _extract(self, text):
        from app.world import _movement_destination_from_narration

        return _movement_destination_from_narration(
            text,
            known_names={"Mosswake Gate"},
            person_names={"Thornrow"},
            current_name="Mosswake Gate",
        )

    def test_proper_noun_destination_wins(self):
        for text, expected in (
            ("You walk into Thistledown Hollow as the mist closes behind you.", "Thistledown Hollow"),
            ("Hours later you reach Redmill Ford, the water loud below.", "Redmill Ford"),
            ("You arrive at Kestrel Bridge just before dark.", "Kestrel Bridge"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self._extract(text), expected)

    def test_terrain_noun_is_the_fallback(self):
        for text, expected in (
            ("The road narrows. You walk into a clearing where the path splits.", "Clearing"),
            ("You leave Thornrow behind and step through into the grove beyond.", "Grove"),
            ("You step into the ruined chapel. Thornrow follows.", "Ruined Chapel"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self._extract(text), expected)

    def test_scenery_without_a_destination_preposition_is_not_a_place(self):
        for text in (
            "The path splits at the clearing, leading both east and north.",
            "You pause, considering. You could take the road east, or head back into town.",
            "The treeline is quiet and the ridge is dark against the sky.",
        ):
            with self.subTest(text=text):
                self.assertEqual(self._extract(text), "")

    def test_never_names_a_place_after_a_known_person_or_the_current_location(self):
        self.assertEqual(self._extract("You walk toward Thornrow and stop."), "")
        self.assertEqual(self._extract("You step back into Mosswake Gate."), "")


class TestMovementContract(unittest.TestCase):
    STATE = {
        "current_location": {"code": "L1", "name": "Mosswake Gate"},
        "locations": [
            {"code": "L1", "name": "Mosswake Gate"},
            {"code": "L2", "name": "Redmill Ford"},
        ],
        "player": {"name": "Ashbound", "sex": ""},
        "settings": {"playthrough_options": {}},
    }

    def test_names_the_current_location_and_the_required_field(self):
        contract = movement_contract(self.STATE, "I head east", "travel")
        self.assertEqual(contract["current_location"]["code"], "L1")
        self.assertIn("move_to_location", contract["rule"])
        self.assertTrue(contract["travel_intent"])

    def test_asks_for_a_name_not_a_code(self):
        """
        Offered a list of codes, a 7B reused the nearest listed code as a stand-in
        for anywhere new: the map stayed two places wide while the prose wandered
        through ruins that were never recorded. Names resolve to existing places
        when they match and create one when they do not.
        """
        contract = movement_contract(self.STATE, "I head east", "travel")
        self.assertIn("known_places", contract)
        self.assertEqual(contract["known_places"], ["Redmill Ford"])
        self.assertNotIn("valid_destination_codes", contract)
        self.assertIn("NAME", contract["rule"])
        self.assertIn("never invent a location code", contract["rule"].lower())

    def test_travel_expectation_only_costs_tokens_on_travel_turns(self):
        travel = movement_contract(self.STATE, "I head east", "travel")
        idle = movement_contract(self.STATE, "I ask about taxes", "conversation")
        self.assertIn("expectation", travel)
        self.assertNotIn("expectation", idle)
        self.assertFalse(idle["travel_intent"])

    def test_current_location_is_not_offered_as_a_destination(self):
        contract = movement_contract(self.STATE, "I head east", "travel")
        self.assertNotIn("Mosswake Gate", contract["known_places"])


class TestPlaceNameHygiene(unittest.TestCase):
    """A live run put a location called `east_road` on the player's map."""

    def test_slugs_become_readable_names(self):
        from app.world import humanize_place_name

        for raw, expected in (
            ("east_road", "East Road"),
            ("north-gate", "North Gate"),
            ("redmill_ford", "Redmill Ford"),
            ("mosswake gate", "Mosswake Gate"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(humanize_place_name(raw), expected)

    def test_names_that_already_read_well_are_untouched(self):
        from app.world import humanize_place_name

        for name in ("Mosswake Gate", "Second Shadow Inn", "Redmill Ford", "Kestrel Bridge"):
            with self.subTest(name=name):
                self.assertEqual(humanize_place_name(name), name)

    def test_slug_and_readable_form_resolve_to_one_location(self):
        from app.world import _find_location_id, _upsert_location

        with connect() as conn:
            a = _upsert_location(conn, "thistle_bridge", "A bridge.")
            b = _find_location_id(conn, "Thistle Bridge")
            c = _find_location_id(conn, "thistle_bridge")
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_bare_directions_are_not_places(self):
        """Live run: `MOVE East` put a location called "East" on the player's map."""
        from app.world import is_plausible_place_name

        for heading in ("East", "the east", "North", "ahead", "Onward", "back",
                        "Nearby", "somewhere", "up", "Beyond", "inside", "the north way"):
            with self.subTest(heading=heading):
                self.assertFalse(is_plausible_place_name(heading))

    def test_real_names_containing_a_direction_survive(self):
        from app.world import is_plausible_place_name

        for name in ("East Road", "Eastgate", "North Quay", "Eastern Reach",
                     "Backwater Mill", "Northolt", "Southwark Steps"):
            with self.subTest(name=name):
                self.assertTrue(is_plausible_place_name(name))

    def test_case_and_article_variants_never_mint_a_duplicate(self):
        """
        Movement is name-driven now, so "the Redmill Ford" must land on the
        existing row rather than creating a near-twin beside it.
        """
        from app.world import _find_location_id, _upsert_location

        with connect() as conn:
            target = _upsert_location(conn, "Kestrel Bridge", "A bridge.")
            before = conn.execute("SELECT COUNT(*) AS n FROM locations").fetchone()["n"]
            for variant in ("Kestrel Bridge", "kestrel bridge", "The Kestrel Bridge",
                            "kestrel_bridge", "KESTREL BRIDGE"):
                with self.subTest(variant=variant):
                    self.assertEqual(_find_location_id(conn, variant), target)
            after = conn.execute("SELECT COUNT(*) AS n FROM locations").fetchone()["n"]
        self.assertEqual(before, after)

    def test_a_known_name_with_a_generic_word_added_folds_back(self):
        """
        Live run: Riverbend Camp, Riverbend Hillcrest, Riverbend Hillcrest Camp
        and Riverbend Hillcrest Post — four map entries the player cannot tell
        apart, for what the prose treated as one area.
        """
        from app.world import _upsert_location

        with connect() as conn:
            base = _upsert_location(conn, "Wyrmcrest Hollow", "A hollow below the ridge.")
            for extension in ("Wyrmcrest Hollow Camp", "Wyrmcrest Hollow Post",
                              "Wyrmcrest Hollow Road", "Wyrmcrest Hollow Outskirts"):
                with self.subTest(extension=extension):
                    self.assertEqual(_upsert_location(conn, extension, ""), base)

    def test_a_leading_descriptor_folds_into_the_same_place(self):
        """Live run: "Ruins by the River" and "Old Ruins by the River" as two map entries."""
        from app.world import _upsert_location

        with connect() as conn:
            base = _upsert_location(conn, "Barrows by the Weir", "Broken stones.")
            for variant in ("Old Barrows by the Weir", "The Barrows by the Weir",
                            "Ancient Barrows by the Weir", "Abandoned Barrows by the Weir"):
                with self.subTest(variant=variant):
                    self.assertEqual(_upsert_location(conn, variant, ""), base)

    def test_a_distinctive_addition_is_still_its_own_place(self):
        """Only generic tail nouns fold; "Chapel" is a real, different location."""
        from app.world import _upsert_location

        with connect() as conn:
            base = _upsert_location(conn, "Harrowfen Reach", "Flat water and reeds.")
            self.assertNotEqual(_upsert_location(conn, "Harrowfen Chapel", ""), base)
            self.assertNotEqual(_upsert_location(conn, "Harrowfen Reach Chapel", ""), base)

    def test_a_genuinely_new_name_still_creates_a_place(self):
        from app.world import _find_location_id

        with connect() as conn:
            before = conn.execute("SELECT COUNT(*) AS n FROM locations").fetchone()["n"]
            made = _find_location_id(conn, "Ravenmoor Steps")
            after = conn.execute("SELECT COUNT(*) AS n FROM locations").fetchone()["n"]
            name = conn.execute("SELECT name FROM locations WHERE id = ?", (made,)).fetchone()["name"]
        self.assertEqual(after, before + 1)
        self.assertEqual(name, "Ravenmoor Steps")


class TestOpcodeAliases(unittest.TestCase):
    """One typo'd opcode used to raise and discard every op in the turn."""

    def test_near_miss_opcodes_map_onto_the_closed_list(self):
        from app.turn_dsl import normalize_opcode

        for raw, expected in (("MOV", "MOVE"), ("GOTO", "MOVE"), ("LOCNEW", "LOC_NEW"),
                              ("npc_new", "NPC_NEW"), ("GIVE", "GRANT"), ("EXP", "XP")):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_opcode(raw), expected)
        self.assertEqual(normalize_opcode("BANANA"), "")

    def test_one_bad_line_does_not_discard_the_rest_of_the_turn(self):
        from app.turn_dsl import parse_ops

        ops = parse_ops('SCENE travel\nMOV L2\nBANANA yes\nFOCUS event "a thing"')
        self.assertEqual([op["op"] for op in ops], ["SCENE", "MOVE", "FOCUS"])

    def test_an_entirely_unrecognizable_block_still_fails(self):
        """Wrong output format must retry, not silently produce an empty turn."""
        from app.turn_dsl import TurnDslError, parse_ops

        with self.assertRaises(TurnDslError):
            parse_ops("BANANA yes\nWOMBAT no")


class TestReplacementNameCollisions(unittest.TestCase):
    def test_repaired_names_do_not_collide_with_live_npcs(self):
        """A live run produced two NPCs both called "Saltbin" from a 20x20 pool."""
        from app.world import name_seed, unique_person_name

        with connect() as conn:
            loc = conn.execute("SELECT id FROM locations WHERE name = 'Mosswake Gate'").fetchone()["id"]
            names = []
            for i in range(12):
                name = unique_person_name(conn, name_seed("collide", i))
                self.assertNotIn(name.lower(), [n.lower() for n in names])
                names.append(name)
                conn.execute(
                    "INSERT INTO npcs (code, location_id, name, role) VALUES (?, ?, ?, 'local')",
                    (f"Q{i}", loc, name),
                )
        self.assertEqual(len(set(names)), len(names))


class TestMenuEndingTrim(unittest.TestCase):
    """
    A 7B restates the player's options as a menu on ~1/4 of turns and did not
    stop when the system prompt forbade it. The UI already asks the player what
    they want to do, so these closers carry nothing.
    """

    BODY = (
        "You push the gate open and the hinge screams. Thornrow watches from the wall, "
        "saying nothing, and the rain has not let up since noon. The yard is churned to mud "
        "and the cart tracks run east, deep and fresh. Somewhere behind the stable a dog "
        "starts up and is hushed. Your boots are already soaked through to the sock. "
    ) * 4

    def test_removes_stock_closers(self):
        from app.llm import _trim_menu_ending

        for closer in (
            "The choice is yours.",
            "The decision is yours.",
            "What will you do next?",
            "What do you do?",
            "Do you approach the hooded figure, or continue on the road?",
            "Will you push forward, or turn back toward the gate?",
        ):
            with self.subTest(closer=closer):
                out, removed = _trim_menu_ending(self.BODY + closer)
                self.assertEqual(removed, 1)
                self.assertNotIn(closer, out)
                self.assertTrue(out.endswith("sock."))

    def test_removes_a_menu_split_across_two_sentences(self):
        """Live: "You could approach the group... Or, you could continue down the road." """
        from app.llm import _trim_menu_ending

        out, removed = _trim_menu_ending(
            self.BODY
            + "You could approach the group and ask for more information. "
            "Or, you could continue down the road, keeping an eye on the settlement."
        )
        self.assertEqual(removed, 2)
        self.assertNotIn("You could", out)
        self.assertTrue(out.endswith("sock."))

    def test_perception_is_description_not_an_offered_action(self):
        """"You could hear the mill wheel" closes a scene; it does not offer a choice."""
        from app.llm import _trim_menu_ending

        for ending in (
            "You could hear the mill wheel turning somewhere behind the hedge.",
            "You could see the smoke from three chimneys.",
            "You could almost taste the salt on the wind.",
        ):
            with self.subTest(ending=ending):
                _, removed = _trim_menu_ending(self.BODY + ending)
                self.assertEqual(removed, 0)

    def test_leaves_ordinary_prose_alone(self):
        from app.llm import _trim_menu_ending

        for ending in (
            "Thornrow spits into the mud and walks away.",
            "The lantern gutters out, and the yard goes dark.",
            "You can almost imagine the traveler who left it behind.",
            "He asks whether you have seen the courier, or anyone at all on the east road.",
        ):
            with self.subTest(ending=ending):
                text = self.BODY + ending
                out, removed = _trim_menu_ending(text)
                self.assertEqual(removed, 0)
                self.assertEqual(out, text.rstrip())

    def test_never_trims_a_short_scene_below_the_floor(self):
        from app.llm import _trim_menu_ending

        out, removed = _trim_menu_ending("You nod. The choice is yours.")
        self.assertEqual(removed, 0)
        self.assertIn("choice is yours", out)

    def test_stops_after_two_sentences(self):
        from app.llm import _trim_menu_ending

        out, removed = _trim_menu_ending(
            self.BODY + "What do you do? The choice is yours. Will you go, or stay?"
        )
        self.assertLessEqual(removed, 2)

    def test_removes_a_trailing_option_list_and_its_lead_in(self):
        """Live run: 5/24 turns closed with a markdown menu of choices."""
        from app.llm import _trim_option_list

        text = (
            self.BODY
            + "You can take several paths east. You could:\n"
            "- Follow the main road through the forest.\n"
            "- Head toward the northern edge, where lights were seen.\n"
            "- Take the secluded path south toward the ruins.\n"
        )
        out, removed = _trim_option_list(text)
        self.assertGreaterEqual(removed, 3)
        self.assertNotIn("Follow the main road", out)
        self.assertNotIn("You could:", out)
        self.assertTrue(out.endswith("sock."))

    def test_numbered_lists_count_too(self):
        from app.llm import _trim_option_list

        text = self.BODY + "\n1. Approach the figure and ask their name.\n2. Keep walking east.\n"
        _, removed = _trim_option_list(text)
        self.assertEqual(removed, 2)

    def test_a_list_with_prose_after_it_is_left_alone(self):
        """A notice or ledger the player is reading is not a menu."""
        from app.llm import _trim_option_list

        text = (
            self.BODY
            + "\n- bread, two coppers\n- salt, four\n\n"
            "You step back and Thornrow spits into the mud, unimpressed by the prices."
        )
        out, removed = _trim_option_list(text)
        self.assertEqual(removed, 0)
        self.assertIn("bread, two coppers", out)

    def test_segments_are_rebuilt_to_match_trimmed_narration(self):
        from app.llm import _apply_menu_trim

        turn = {
            "narration": self.BODY + "The choice is yours.",
            "narration_segments": [{"label": "paragraph", "text": "stale"}],
            "player": {"gold_delta": 4},
        }
        out = _apply_menu_trim(turn)
        self.assertEqual(out["_menu_trimmed"], 1)
        self.assertNotIn("choice is yours", out["narration"])
        self.assertNotIn("stale", json.dumps(out["narration_segments"]))
        self.assertEqual(out["player"]["gold_delta"], 4)


class TestSeededNpcVariety(unittest.TestCase):
    """
    Roles for prose-seeded NPCs used to be a fixed four-item cycle starting
    "hooded stranger", "cloaked local". Since a scene rarely seeds more than two
    faces, those two won almost every time: 24 of 27 NPCs across three live runs.
    It also fed back on itself — the seeder wrote hooded strangers into the cast,
    the cast went into the next prompt, and the model kept writing hooded figures.
    """

    def _place(self, name, summary=""):
        from app.world import _upsert_location

        with connect() as conn:
            return _upsert_location(conn, name, summary)

    def test_role_pool_follows_the_kind_of_place(self):
        from app.world import _SEED_ROLE_POOLS, _seed_role_pool

        cases = {
            "water": ("Redmill Ford", "A river crossing with a quay."),
            "indoor": ("The Broken Oar", "A low taproom off the hall."),
            "wilderness": ("Thistle Woods", "Deep forest and thicket."),
            "settlement": ("Cinder Market", "A crowded market square in the city."),
        }
        for expected, (name, summary) in cases.items():
            with self.subTest(place=name):
                loc = self._place(name, summary)
                with connect() as conn:
                    pool = _seed_role_pool(conn, loc)
                # Pools are indexed era-first now; these worlds have no
                # tech_level set, so they resolve to preindustrial -- the shape
                # every world used to get unconditionally.
                self.assertIs(pool, _SEED_ROLE_POOLS["preindustrial"][expected])

    def test_a_passing_mention_of_the_road_does_not_make_a_town_wilderness(self):
        """Scored, not first-hit: town summaries mention roads constantly."""
        from app.world import _SEED_ROLE_POOLS, _seed_role_pool

        loc = self._place("Ashford Gate", "A frontier gate-town where caravans wait by the road.")
        with connect() as conn:
            self.assertIs(
                _seed_role_pool(conn, loc), _SEED_ROLE_POOLS["preindustrial"]["settlement"]
            )

    def test_appearance_never_becomes_the_role(self):
        from app.world import _appearance_note, _seed_role_for

        loc = self._place("Wynd Street", "A narrow street in the town quarter.")
        with connect() as conn:
            role = _seed_role_for(conn, loc, "a hooded figure", 0, salt="scene")
        self.assertNotIn("hooded", role.lower())
        self.assertNotIn("cloaked", role.lower())
        self.assertNotIn("stranger", role.lower())
        # ...but it is not thrown away either
        self.assertIn("hooded", _appearance_note("a hooded figure").lower())

    def test_an_explicit_occupation_in_the_prose_still_wins(self):
        from app.world import _seed_role_for

        loc = self._place("Tallow Row", "A street of shops in the town.")
        with connect() as conn:
            for hint, expected in (
                ("the merchant says", "merchant"),
                ("a guard", "guard"),
                ("the innkeeper asks", "innkeeper"),
            ):
                with self.subTest(hint=hint):
                    self.assertEqual(_seed_role_for(conn, loc, hint, 0, salt="s"), expected)

    def test_faces_seeded_into_one_place_get_different_jobs(self):
        from app.world import _seed_role_for, create_shell_npc, name_seed

        loc = self._place("Brimmer Square", "A market square in the town.")
        roles = []
        with connect() as conn:
            for i in range(5):
                role = _seed_role_for(conn, loc, "", i, salt="crowd")
                roles.append(role)
                create_shell_npc(conn, loc, role=role, seed=name_seed("variety", i))
        self.assertEqual(len(set(roles)), len(roles), roles)

    def test_shell_names_are_unique_world_wide_not_per_location(self):
        """
        The collision check was scoped to one location, so a run with sixteen
        seeded faces produced three separate people all called "Grainwick".
        """
        from app.world import _seed_role_for, _upsert_location, create_shell_npc, name_seed

        with connect() as conn:
            places = [
                _upsert_location(conn, f"{prefix} Town", "A town square in the city.")
                for prefix in ("Alpha", "Beta", "Gamma")
            ]
            names = []
            for i in range(18):
                loc = places[i % len(places)]
                shell = create_shell_npc(
                    conn,
                    loc,
                    presence="event_worthy",
                    role=_seed_role_for(conn, loc, "", i, salt="dup"),
                    seed=name_seed("dup-test", i),
                )
                names.append(str(shell["name"]))
        duplicates = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual(duplicates, [], f"duplicate shell names: {duplicates}")

    def test_seeded_roles_are_stable_across_processes(self):
        """Rewind must reproduce the same crowd."""
        code = (
            "import sys, os, tempfile; sys.path.insert(0, r'%s');"
            "t=tempfile.mkdtemp();"
            "os.environ['AI_RPG_DB']=t+'/w.db'; os.environ['AI_RPG_SOURCE_INDEX']=t+'/si';"
            "os.environ['AI_RPG_SKILL_LIBRARY']=t+'/s.json';"
            "from app.db import connect, init_db; from app import world; init_db();"
            "conn=connect().__enter__();"
            "loc=world._upsert_location(conn,'Brack Quay','A dock and quay.');"
            "print([world._seed_role_for(conn, loc, '', i, salt='x') for i in range(3)])"
            % ROOT
        )
        outs = set()
        for hash_seed in ("0", "1", "12345"):
            env = {**os.environ, "PYTHONHASHSEED": hash_seed}
            outs.add(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env).stdout.strip())
        self.assertEqual(len(outs), 1, f"seeded roles drifted: {outs}")


class TestNpcIdentityAcrossLocations(unittest.TestCase):
    """
    The name lookup in _upsert_npc was scoped to one location, so a live run
    ended with two NPCs both called "Aria", both bakers, in different places.
    One name is one person; people also travel, so the match moves them.
    """

    def test_the_same_name_elsewhere_is_the_same_person(self):
        from app.world import _upsert_location, _upsert_npc

        with connect() as conn:
            _upsert_location(conn, "Tallow Gate", "A gate.")
            _upsert_location(conn, "Kettle Camp", "A camp.")
            first = _upsert_npc(conn, {"name": "Wrenna", "role": "baker", "location": "Tallow Gate"})
            again = _upsert_npc(conn, {"name": "Wrenna", "role": "baker", "location": "Kettle Camp"})
            lower = _upsert_npc(conn, {"name": "wrenna", "role": "baker", "location": "Kettle Camp"})
        self.assertEqual(first, again)
        self.assertEqual(first, lower)

    def test_a_matched_npc_follows_the_scene(self):
        from app.world import _upsert_location, _upsert_npc

        with connect() as conn:
            _upsert_location(conn, "Pellow Gate", "A gate.")
            target = _upsert_location(conn, "Pellow Wharf", "A wharf.")
            npc = _upsert_npc(conn, {"name": "Selk", "role": "porter", "location": "Pellow Gate"})
            _upsert_npc(conn, {"name": "Selk", "role": "porter", "location": "Pellow Wharf"})
            where = conn.execute("SELECT location_id FROM npcs WHERE id = ?", (npc,)).fetchone()
        self.assertEqual(int(where["location_id"]), target)

    def test_different_names_stay_different_people(self):
        from app.world import _upsert_location, _upsert_npc

        with connect() as conn:
            _upsert_location(conn, "Marrow Gate", "A gate.")
            a = _upsert_npc(conn, {"name": "Halden", "role": "guard", "location": "Marrow Gate"})
            b = _upsert_npc(conn, {"name": "Bricke", "role": "guard", "location": "Marrow Gate"})
        self.assertNotEqual(a, b)


class TestAntiRepetition(unittest.TestCase):
    def test_entity_names_are_never_put_on_the_avoid_list(self):
        """
        The avoid-list was raw word frequency, so a turn spent talking to
        Larkcoil at Redmill Ford came back telling the model to stop saying
        "larkcoil", "redmill", "ford" — asking the narrator to stop naming its
        own world, directly against the continuity work.
        """
        from app.prompts import anti_repetition_block

        block = anti_repetition_block(
            {
                "last_narration": (
                    "Larkcoil waits at Redmill Ford. Larkcoil watches the water. "
                    "Redmill Ford is loud tonight, and Larkcoil says nothing at all."
                ),
                "overused_words": ["larkcoil", "redmill", "hooded"],
                "player": {"name": "Ashen Courier", "public_name": "the Ashbound"},
                "current_location": {"name": "Redmill Ford"},
                "locations": [{"name": "Redmill Ford", "npcs": [{"name": "Larkcoil"}]}],
            }
        ).lower()
        for name in ("larkcoil", "redmill", "ashbound", "courier"):
            self.assertNotIn(name, block, f"{name} must stay usable")
        self.assertIn("hooded", block)

    def test_run_wide_tics_reach_the_avoid_list(self):
        """A word used once per turn never trips a single-turn threshold."""
        from app.prompts import anti_repetition_block

        block = anti_repetition_block(
            {
                "last_narration": "The gate stands open and the mud has dried to ruts.",
                "overused_words": ["hooded", "shadows", "figure"],
            }
        ).lower()
        for tic in ("hooded", "shadows", "figure"):
            self.assertIn(tic, block)

    def test_tic_detection_needs_real_repetition(self):
        from app.world import narration_tics

        varied = [
            "The cart wheel had split along the rim.",
            "Rain filled the ruts overnight and nobody bailed them.",
            "Someone left a ledger open on the counter.",
            "Bread went up two coppers without warning.",
            "A dog barked itself hoarse behind the stable.",
            "The bell rang late and out of time.",
            "Salt crusted the rope where it met the cleat.",
            "Lamp oil ran thin before the watch changed.",
        ]
        with connect() as conn:
            conn.execute("DELETE FROM journal WHERE kind = 'narration'")
            for i, line in enumerate(varied):
                conn.execute(
                    "INSERT INTO journal (turn, kind, content) VALUES (?, 'narration', ?)",
                    (900 + i, f"A hooded figure waits in the shadows. {line}"),
                )
            tics = narration_tics(conn)
            conn.execute("DELETE FROM journal WHERE kind = 'narration'")
        self.assertIn("hooded", tics)
        self.assertIn("shadows", tics)
        # Words that appeared in exactly one scene are not tics.
        for once in ("ledger", "coppers", "stable", "cleat"):
            self.assertNotIn(once, tics)


class TestNarrativeVoice(unittest.TestCase):
    def test_pronouns_default_to_neutral_when_sex_is_not_clearly_stated(self):
        self.assertEqual(player_pronouns("female")["subject"], "she")
        self.assertEqual(player_pronouns("male")["subject"], "he")
        for vague in ("", None, "unspecified", "sexless or constructed", "varies by form", "intersex"):
            with self.subTest(sex=vague):
                self.assertEqual(player_pronouns(vague)["subject"], "they")

    def test_contract_states_person_and_pronouns(self):
        state = {"player": {"name": "Ashbound", "public_name": "Ashbound", "sex": "female"}, "settings": {}}
        contract = narrative_voice_contract(state)
        self.assertEqual(contract["person"], "second")
        self.assertEqual(contract["player_pronouns"]["subject"], "she")
        self.assertIn("Ashbound", contract["rule"])

    def test_third_person_narration_is_flagged(self):
        state = {"player": {"name": "Ashbound", "public_name": "Ashbound", "sex": ""}, "settings": {}}
        third = (
            "Ashbound stands at the gate as the rain thickens. Thornrow [[B]] watches her from under his hood, "
            "and her pack feels heavier than it did an hour ago. The guard waves Ashbound through without a word. "
            "She could follow the east road, or turn back toward the market where the crates are still stacked."
        )
        report = check_narrative_voice(third, state)
        self.assertTrue(report["drift"])
        self.assertEqual(report["second_person_refs"], 0)
        self.assertGreaterEqual(report["player_name_as_subject"], 1)

    def test_second_person_narration_is_clean(self):
        state = {"player": {"name": "Ashbound", "public_name": "Ashbound", "sex": ""}, "settings": {}}
        second = (
            "You stand at the gate as the rain thickens. Thornrow [[B]] watches you from under his hood, "
            "and your pack feels heavier than it did an hour ago. The guard waves you through without a word. "
            "You could follow the east road, or turn back toward the market where the crates are still stacked."
        )
        report = check_narrative_voice(second, state)
        self.assertFalse(report["drift"])
        self.assertGreater(report["second_person_refs"], 0)

    def test_a_short_line_is_not_treated_as_drift(self):
        """One-line beats have no room for a "you"; only full narrations count."""
        state = {"player": {"name": "Ashbound", "sex": ""}, "settings": {}}
        self.assertFalse(check_narrative_voice("The door closes.", state)["drift"])


class TestVoiceRepairPlumbing(unittest.TestCase):
    def test_clean_narration_skips_the_retry_entirely(self):
        """The repair costs an extra model pass, so it must not fire on good prose."""
        from app.llm import _ensure_narration_voice

        context = {
            "narrative_voice": narrative_voice_contract(
                {"player": {"name": "Ashbound", "sex": ""}, "settings": {}}
            ),
            "player": {"name": "Ashbound", "sex": ""},
            "settings": {},
        }
        turn = {
            "narration": "You push the gate open. " * 20,
            "player": {"gold_delta": 3},
        }
        # No LLM available in tests; a retry attempt would raise, not return.
        out = _ensure_narration_voice(turn, context, "walk east", "sys", 5, [], "test", None)
        self.assertFalse(out["_voice_check"]["drift"])
        self.assertEqual(out["player"]["gold_delta"], 3)

    def test_splice_keeps_state_and_honours_the_length_ceiling(self):
        from app.llm import MAX_TURN_NARRATION_CHARS, _splice_prose_into_turn

        turn = {"narration": "old", "player": {"gold_delta": 3}, "npcs": [{"code": "A"}]}
        prose = "\n\n".join(f"Paragraph {i}. " + ("word " * 120) for i in range(8))
        out = _splice_prose_into_turn(turn, prose)
        self.assertLessEqual(len(out["narration"]), MAX_TURN_NARRATION_CHARS)
        self.assertEqual(out["player"]["gold_delta"], 3)
        self.assertEqual(out["npcs"], [{"code": "A"}])
        self.assertTrue(out["narration"].startswith("Paragraph 0."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
