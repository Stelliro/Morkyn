"""A group the prose does not count is rolled, filed that many, and the prose says the number (app/unnamed.py).

Stell, 2026-10-24 (CLAUDE.md, Design decisions, under "Unnamed NPCs are stored
and numbered per kind"): "we should be looking at "'s" as if they account for
many, and we should roll a dice on it and stick to it ie. "Gouls lunge at you"
dice roll = 4 = "4 ghouls lunge at you"". The engine rolls the count with its
own seeded dice (unnamed.UNSTATED_DICE), files that many rows, writes the
number into the prose where the group first appears, and keeps to it after.

The mocked figure asks answer as Hermes 3 8B did on the asks measured
(live-eval-5 / live-eval-7): a reply cut at four tokens that opens with yes or
no. On scenery the measured replies were no ("A shadow passes over you.":
figure_kind 'No, in this'); that is the reply given here for the scenery nouns.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-unnamed-counts-"))
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


def _fresh_world():
    from app import db, rng, world

    db.init_db()
    rng.reset_seed_cache()
    world.start_playthrough({"player_name": "Will Tanaka", "start_location": "Radiation Fenced Sanctuary",
                             "special_ability_origin": "none"})


# Hermes 3 8B's replies to these asks (live-eval-5 / live-eval-7), by what the noun is.
_FIGURES = {"ghoul", "raider", "drifter", "wolf", "rat"}
_SCENERY_REPLY = "No, in this"


class _Asker:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system, user, *, trace=None, usage=None, phase="", max_tokens=None):
        self.calls.append((phase, user))
        question = user.split("\n")[-1]
        if phase == "figure_kind":
            return "Yes, \"gh" if any(f'"{f}"' in question for f in _FIGURES) else _SCENERY_REPLY
        if phase == "figure_kind_check":
            return "Yes, a gh" if any(f"the {f} a creature" in question for f in _FIGURES) else "No."
        if phase == "figure_hostile":
            return 'Yes, "a'
        if phase == "figure_speaks":
            return "No."
        if phase == "entity_kind":
            return "person"
        return "no"

    def asked(self, phase):
        return [u for p, u in self.calls if p == phase]


def _play(prose, line, asker=None, summary="A scene."):
    from app import entity_kinds, world
    from app.turn_dsl import parse_dsl_turn

    turn = parse_dsl_turn(f"===NAR===\n{prose}\n\n===OPS===\nSUMMARY: \"{summary}\"\n", line)
    turn["narration"] = prose
    previous = entity_kinds.set_kind_ask(asker or _Asker())
    try:
        entity_kinds.settle_kinds(turn, line)
        state = world.apply_turn(turn, line, input_kind="player")
    finally:
        entity_kinds.set_kind_ask(previous)
    return turn, state


def _q(sql, *params):
    from app import db

    with db.connect().closing() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _names():
    return [r["name"] for r in _q("SELECT name FROM npcs WHERE kind != '' ORDER BY id")]


def _stored_narration():
    rows = _q("SELECT content FROM journal WHERE kind = 'narration' ORDER BY id DESC LIMIT 1")
    return rows[0]["content"] if rows else ""


def _stored_summary():
    rows = _q("SELECT summary FROM turn_summaries ORDER BY id DESC LIMIT 1")
    return rows[0]["summary"] if rows else ""


def _count_rolls():
    return _q("SELECT * FROM dice_rolls WHERE source = 'unnamed_count' ORDER BY id")


class TheBarePluralIsAGroup(unittest.TestCase):
    def test_a_bare_plural_opening_its_clause_is_a_mention(self):
        from app import unnamed

        def read(text):
            return [(m["kind"], m["form"], m["stated"], m["phrase"]) for m in unnamed.mentions(text)]

        self.assertEqual(read("Ghouls lunge at you."), [("ghoul", "count", False, "Ghouls")])
        self.assertEqual(read("Then raiders step out of the wreck."), [("raider", "count", False, "raiders")])
        # Not the clause's subject, a participle phrase, or a name: no group.
        self.assertEqual(read("The ghoul snarls and lunges at you."), [("ghoul", "the", True, "The ghoul")])
        self.assertEqual(read("Their milky eyes stare at you."), [])
        self.assertEqual([k for k, *_ in read("A deathclaw charges at you, claws raking the asphalt.")], ["deathclaw"])


class TheCountIsRolledAndWritten(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_ghouls_lunge_at_you_with_a_roll_of_four(self):
        from app import unnamed

        with mock.patch.object(unnamed, "UNSTATED_DICE", "4"):
            turn, state = _play("Ghouls lunge at you.", "i look around", summary="Ghouls lunge at the player.")
        self.assertEqual(_names(), ["Ghoul 1", "Ghoul 2", "Ghoul 3", "Ghoul 4"])
        self.assertEqual(turn["narration"], "Four ghouls lunge at you.")
        self.assertEqual([s["text"] for s in turn["narration_segments"]], ["Four ghouls lunge at you."])
        self.assertEqual(_stored_narration(), "Four ghouls lunge at you.")
        self.assertEqual(turn["turn_summary"], "Four ghouls lunge at the player.")
        self.assertEqual(_stored_summary(), "Four ghouls lunge at the player.")
        # The roll is in the dice audit and with the turn's dice, like every roll.
        rolls = _count_rolls()
        self.assertEqual([(r["value"], r["notation"], r["band"]) for r in rolls], [(4, "4", "ghoul")])
        self.assertTrue(any("figure_count (ghoul)" in line for line in (state.get("dice_rolls") or {}).get("lines", [])),
                        state.get("dice_rolls"))
        dice_lines = _q("SELECT content FROM journal WHERE kind = 'dice'")
        self.assertTrue(any("figure_count (ghoul)" in r["content"] for r in dice_lines), dice_lines)

    def test_the_whole_turn_says_four_the_reply_and_the_trace(self):
        import json

        from app import entity_kinds, unnamed, world
        from app.turn_dsl import parse_dsl_turn

        line = "i look around"
        draft = parse_dsl_turn('===NAR===\nGhouls lunge at you.\n\n===OPS===\nSUMMARY: "Ghouls lunge at the player."\n',
                               line)
        previous = entity_kinds.set_kind_ask(_Asker())
        try:
            with mock.patch.object(world, "generate_turn", return_value=draft), \
                    mock.patch.object(unnamed, "UNSTATED_DICE", "4"):
                out = world.play_turn(line)
        finally:
            entity_kinds.set_kind_ask(previous)
        self.assertEqual(out["turn"]["narration"], "Four ghouls lunge at you.")
        self.assertEqual([s["text"] for s in out["turn"]["narration_segments"]], ["Four ghouls lunge at you."])
        self.assertEqual(out["turn"]["turn_summary"], "Four ghouls lunge at the player.")
        traces = sorted(world.model_trace_dir().glob("turn-*-player.json"), key=lambda p: p.stat().st_mtime)
        trace = json.loads(traces[-1].read_text(encoding="utf-8"))
        self.assertEqual(trace["final_turn"]["narration"], "Four ghouls lunge at you.")
        self.assertEqual(_stored_narration(), "Four ghouls lunge at you.")
        self.assertEqual(len(_names()), 4)

    def test_a_pack_of_ghouls_and_some_raiders(self):
        from app import unnamed

        with mock.patch.object(unnamed, "UNSTATED_DICE", "4"):
            turn, _ = _play("A pack of ghouls circles you, snarling.", "i draw my knife")
        self.assertEqual(turn["narration"], "A pack of four ghouls circles you, snarling.")
        self.assertEqual(len([n for n in _names() if n.startswith("Ghoul")]), 4)
        with mock.patch.object(unnamed, "UNSTATED_DICE", "3"):
            turn, _ = _play("Some raiders step out from the wreck and level their rifles at you.", "i freeze")
        self.assertEqual(turn["narration"], "Three raiders step out from the wreck and level their rifles at you.")
        self.assertEqual([n for n in _names() if n.startswith("Raider")], ["Raider 1", "Raider 2", "Raider 3"])
        with mock.patch.object(unnamed, "UNSTATED_DICE", "2"):
            turn, _ = _play("A few drifters shuffle toward you from the road.", "i wave")
        self.assertEqual(turn["narration"], "Two drifters shuffle toward you from the road.")

    def test_a_stated_count_is_not_rolled_or_rewritten(self):
        prose = "Two raiders step out from behind the wreck and level their rifles at you."
        turn, _ = _play(prose, "i stop")
        self.assertEqual(_names(), ["Raider 1", "Raider 2"])
        self.assertEqual(turn["narration"], prose)
        self.assertEqual(_count_rolls(), [])

    def test_the_roll_is_the_engines_seeded_dice_and_a_regenerate_rolls_the_same(self):
        from app import world

        turn, _ = _play("Ghouls lunge at you.", "i look around")
        first = (_names(), turn["narration"], [r["rolls"] for r in _count_rolls()])
        count = len(first[0])
        self.assertTrue(2 <= count <= 5, first)
        self.assertEqual(_count_rolls()[0]["notation"], "1d4+1")
        world.rewind_last_turn()
        self.assertEqual(_names(), [])
        self.assertEqual(_count_rolls(), [])
        self.assertNotIn("ghouls lunge", _stored_narration().lower())
        for _ in range(2):
            turn, _ = _play("Ghouls lunge at you.", "i look around")
            self.assertEqual((_names(), turn["narration"], [r["rolls"] for r in _count_rolls()]), first)
            world.rewind_last_turn()


class StickToIt(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_later_turns_keep_the_count(self):
        from app import unnamed

        with mock.patch.object(unnamed, "UNSTATED_DICE", "4"):
            _play("Ghouls lunge at you.", "i look around")
        self.assertEqual(len(_names()), 4)
        # "the ghouls" refers back; "some ghouls" with four here adds none; nothing more is rolled.
        turn, _ = _play("The ghouls circle you, hissing.", "i back away")
        self.assertEqual(turn["narration"], "The ghouls circle you, hissing.")
        turn, _ = _play("Some ghouls claw at your armor.", "i shove them off")
        self.assertEqual(turn["narration"], "Some ghouls claw at your armor.")
        self.assertEqual(len(_names()), 4)
        self.assertEqual(len(_count_rolls()), 1)
        _play("Another ghoul drops from the ceiling behind you.", "i turn")
        self.assertEqual(_names(), ["Ghoul 1", "Ghoul 2", "Ghoul 3", "Ghoul 4", "Ghoul 5"])


class SceneryIsNotCounted(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_shadows_and_footsteps_file_nothing_and_stay_as_written(self):
        for prose in ("Shadows dance on the wall.", "Footsteps echo down the hall.",
                      "Shadows dance on the wall around you.", "Footsteps echo behind you."):
            asker = _Asker()
            turn, _ = _play(prose, "i wait", asker)
            self.assertEqual(turn["narration"], prose)
            self.assertEqual(_names(), [], prose)
            # Only both asks saying yes files a figure; the check is never reached on a "no".
            self.assertEqual(asker.asked("figure_kind_check"), [], prose)
        self.assertEqual(_count_rolls(), [])


class _YesAsker(_Asker):
    """Says yes to every figure ask: whatever is read as a kind would be filed."""

    def __call__(self, system, user, *, trace=None, usage=None, phase="", max_tokens=None):
        self.calls.append((phase, user))
        if phase in ("figure_kind", "figure_kind_check", "figure_hostile"):
            return "Yes."
        return super().__call__(system, user, trace=trace, usage=usage, phase=phase, max_tokens=max_tokens)


class QuantityWords(unittest.TestCase):
    """The words that only say how many (reviewer probes on d94d240)."""

    def setUp(self):
        _fresh_world()

    def _rolled(self, prose, dice="5"):
        from app import unnamed

        with mock.patch.object(unnamed, "UNSTATED_DICE", dice):
            turn, _ = _play(prose, "i wait", _YesAsker())
        return turn["narration"], _names()

    def test_a_couple_of_and_a_pair_of_are_a_stated_two(self):
        for prose in ("A couple of raiders step toward you.", "A pair of raiders step toward you."):
            _fresh_world()
            narration, names = self._rolled(prose)
            self.assertEqual(narration, prose)
            self.assertEqual(names, ["Raider 1", "Raider 2"], prose)
            self.assertEqual(_count_rolls(), [], prose)

    def test_a_quantity_word_gives_way_to_the_rolled_number(self):
        cases = {
            "Countless rats swarm over you.": ("Five rats swarm over you.", "Rat"),
            "Numerous raiders surround you.": ("Five raiders surround you.", "Raider"),
            "A handful of raiders step toward you.": ("Five raiders step toward you.", "Raider"),
            "Dozens of ghouls pour into the street toward you.": ("Five ghouls pour into the street toward you.", "Ghoul"),
            "Many ghouls lunge at you.": ("Five ghouls lunge at you.", "Ghoul"),
            "Lots of raiders surround you.": ("Five raiders surround you.", "Raider"),
            "Scores of rats pour toward you.": ("Five rats pour toward you.", "Rat"),
            "A few drifters shuffle toward you.": ("Five drifters shuffle toward you.", "Drifter"),
            "Several ghouls lunge at you.": ("Five ghouls lunge at you.", "Ghoul"),
            "Some raiders close in on you.": ("Five raiders close in on you.", "Raider"),
        }
        for prose, (want, kind) in cases.items():
            _fresh_world()
            narration, names = self._rolled(prose)
            self.assertEqual(narration, want, prose)
            self.assertEqual(names, [f"{kind} {n}" for n in range(1, 6)], prose)
            self.assertEqual(len(_count_rolls()), 1, prose)

    def test_a_group_noun_keeps_its_noun(self):
        for prose, want in (("A pack of ghouls lunges at you.", "A pack of five ghouls lunges at you."),
                            ("A horde of ghouls surges at you.", "A horde of five ghouls surges at you."),
                            ("A group of raiders aims at you.", "A group of five raiders aims at you.")):
            _fresh_world()
            narration, names = self._rolled(prose)
            self.assertEqual(narration, want)
            self.assertEqual(len(names), 5, prose)

    def test_the_summary_drops_the_quantity_word_too(self):
        from app import unnamed

        with mock.patch.object(unnamed, "UNSTATED_DICE", "3"):
            turn, _ = _play("Countless rats swarm over you.", "i wait", _YesAsker(),
                            summary="The player is swarmed by countless rats.")
        self.assertEqual(turn["turn_summary"], "The player is swarmed by three rats.")


class NamesAreNoBarePlural(unittest.TestCase):
    """A name ending in -s at a sentence start (reviewer probes: Carlos, James, Silas, Thomas)."""

    def setUp(self):
        _fresh_world()

    def test_names_are_not_read_as_a_kind(self):
        from app import unnamed

        def kinds(text, names=()):
            return [m["kind"] for m in unnamed.mentions(text, (), names)]

        # Agreement: a singular verb has a singular subject.
        self.assertEqual(kinds("Carlos steps toward you."), [])
        self.assertEqual(kinds("James waves you over."), [])
        self.assertEqual(kinds("Silas glares at you."), [])
        self.assertEqual(kinds("Thomas lunges at you."), [])
        # Another capitalised word, a [[code]], the prose naming it inside a sentence, the roster.
        self.assertEqual(kinds("Carlos Khan turned to you."), [])
        self.assertEqual(kinds("Thomas [[N3]] turned to you."), [])
        self.assertEqual(kinds("Silas turned to you. You nod to Silas."), [])
        self.assertEqual(kinds("Carlos looked up at you.", {"carlos"}), [])
        # A relative pronoun's verb and a possessive are no group either.
        self.assertEqual(kinds("You aim at the doctor, who remains calm."), [])
        self.assertEqual(kinds("Raiders' bullets whiz past you."), [])
        # A real bare plural still is one, in the past tense too.
        self.assertEqual(kinds("Ghouls lunged at you."), ["ghoul"])

    def test_a_roster_name_files_nothing_and_stays_as_written(self):
        from app import db, unnamed

        with db.connect().closing() as conn:
            loc = conn.execute("SELECT current_location_id FROM player LIMIT 1").fetchone()[0]
            conn.execute("INSERT INTO npcs (code, location_id, name) VALUES ('N90', ?, 'Carlos Reyes')", (loc,))
            conn.commit()
        prose = "Carlos looked up at you from the counter."
        asker = _YesAsker()
        with mock.patch.object(unnamed, "UNSTATED_DICE", "4"):
            turn, _ = _play(prose, "i wave", asker)
        self.assertEqual(turn["narration"], prose)
        self.assertEqual(_names(), [])
        self.assertEqual(_count_rolls(), [])
        self.assertFalse(any('"carlo"' in u for u in asker.asked("figure_kind")), asker.calls)


if __name__ == "__main__":
    unittest.main()


class MemoriesAreNotFiguresHereNow(unittest.TestCase):
    """The reviewer of 4075bfc: a memory or the past was filed as figures present and rolled."""

    def _kinds(self, text):
        from app.unnamed import mentions

        return [(m["kind"], m["stated"]) for m in mentions(text)]

    def test_the_players_own_perfect_is_a_memory(self):
        self.assertEqual(self._kinds("You have killed many ghouls in your time."), [])
        self.assertEqual(self._kinds("You've seen raiders like him before."), [])
        self.assertEqual(self._kinds("You have seen some raiders like him before."), [])

    def test_ago_is_the_past(self):
        self.assertEqual(self._kinds("Hundreds of years ago, ghouls roamed these tunnels around you."), [])

    def test_many_is_not_a_count(self):
        self.assertEqual(self._kinds("So many ghouls lunge at you that you lose count."), [])
        self.assertEqual(self._kinds("You wonder how many raiders remain near you."), [])

    def test_the_scene_now_is_still_filed(self):
        self.assertEqual(self._kinds("Ghouls lunge at you."), [("ghoul", False)])
        self.assertEqual(self._kinds("Ghouls have surrounded you."), [("ghoul", False)])
        self.assertEqual(self._kinds("Countless rats swarm over you."), [("rat", False)])
