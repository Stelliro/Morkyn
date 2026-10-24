"""base100 (Hermes 3 8B, player Isk Tarrow), turns 11-24: the creature with no row, and the gate that cut the player's act.

Two fault classes, fixed at the place each is decided (CLAUDE.md: engine
first, no narrator prompt text, no word list for one phrasing, a cut is last
and never of the player's own words or act):

1. A creature the prose shows acting had no row, so the player's blows at it
   landed on a bystander. T22 (trace -000023): "a massive beast - a dire wolf
   ... The dire wolf lunges" filed nothing (a "the" form was never minted).
   T23 (-000024): "I draw my knife and stab at the dire wolf's throat" was
   aimed by the trigger at Orabel [[E]], the one row present ("Your strike
   falls short of Orabel [[E]]."). T24 (-000025): "I ignore Orabel and slash
   at the dire wolf circling us in the fog" rolled a critical success into
   Orabel (health 21 -> 17). T14 (-000015): "Seagulls call overhead" was
   filed as person row D from the named-speaker hint, and the fish-seller was
   bound to it (T18).
2. The player-words gate cut the sentences that performed the act the player
   asked for. T17 (-000018): "I hand her the coin, take the herring and eat
   it." lost "She pockets the coin ... You take a glistening herring ... as
   you eat" as the reply to an invented "you ask.". T24: "you slash at the
   wolf" went with an invented decision. T11 (-000012): the QUEST op "Watch
   the North Docks" went with the tail that answered an invented "What kind
   of trouble?", though the line asked for a contract.

The prose and lines below are the run's own, verbatim.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-base100-wolf-"))
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

T22_LINE = "I press on along the tracks until I come upon the beast."
T22_PROSE = (
    "The storm continues as you press on along the beast's trail. The rain has washed away most of the spoor, but "
    "you can still make out a few hoofprints in the mud. They lead towards Saltmarrow, as if the creature has been "
    "lurking just outside the town, perhaps waiting for the cover of darkness to strike.\n\n"
    "You follow the trail cautiously. The beast seems to grow more restless with each passing moment, as if it "
    "senses your presence. Suddenly, a low growl echoes through the trees ahead.\n\n"
    "You freeze, your heart pounding in your chest. There, barely visible in the gloom, stands a massive beast - a "
    "dire wolf, its fur matted and dripping with rain. It snarls, revealing rows of sharp teeth, and takes a step "
    "towards you.\n\n"
    "The dire wolf lunges, and you steel yourself for the fight to come."
)
T23_LINE = "I draw my knife and stab at the dire wolf's throat as it comes in."
T23_PROSE = (
    "You crouch by the roadside, knife in hand, scanning the shadows for any sign of the dire wolf that attacked "
    "last night. The grey light of dawn barely penetrates the thick fog that lies over the road ahead. Saltmarrow "
    "lies just a few miles behind you, but the road before you is empty, and the silence is broken only by the "
    "occasional drip of water from the overhanging branches. The fog muffles any sound, leaving you on edge.\n"
    "Orabel emerges from the fog behind you, wiping her hands on her apron. \"Morning, stranger,\" she says, giving "
    "you a curious look. \"You're not heading into the swamp, are you? That fog'll hide all sorts of dangers.\""
)
T24_LINE = "I ignore Orabel and slash at the dire wolf circling us in the fog."
T24_DRAFT = (
    "You stand outside Saltmarrow, the fog swirling around your feet as you search the muddy ground for the dire "
    "wolf's trail. Orabel, the kitchen hand, watches you warily from a distance, her hand resting on the knife at "
    "her belt. The fog is thick and the grey light of early morning casts long shadows across the muddy street.\n\n"
    "The dire wolf circles, its eyes glinting through the fog. You've seen its like before - wild and untamed, with "
    "a hunger in its eyes that promises death to those it meets. It snarls and growls, circling closer.\n\n"
    "You know you need to end this, to kill the wolf before it kills again. Orabel watches, her stance tense and "
    "ready. She's armed and willing to fight, but this is your task. You must face the wolf alone.\n\n"
    "\"Go!\" Orabel calls out. \"I'll watch your back!\"\n\n"
    "You nod, your hand tightening around your dagger. The fog swirls as you lunge forward, your boots splashing in "
    "the mud. With a roar, you slash at the wolf, aiming for its throat. Your blade bites deep, drawing blood. The "
    "wolf howls in pain and rage, turning to face you.\n\n"
    "You stand ready, waiting for the next attack. The wolf lunges, jaws snapping. You sidestep and slash again, "
    "keeping it at bay. You dance around each other in the fog, a deadly ballet of steel and fury.\n\n"
    "Orabel watches from a distance, her face etched with concern. She knows this is your fight, but she's ready to "
    "help if you need it. For now, you face the wolf alone, your blade your only ally against the monster's fury."
)
T14_LINE = "I pick along the pilings at the tide line for anything the water left behind."
T14_PROSE = (
    "The grey light of dawn washes over the pilings as you sift through the sand and shells at your feet. You find a "
    "few coins, a bent silver spoon, and the rusting edge of an old belt buckle. The water laps at the base of the "
    "wooden posts, leaving a sheen of foam on the slick stones below. Seagulls call overhead as they ride the "
    "currents above the harbour.\n\n"
    "You continue picking along the edge of the waterline, hoping for anything the sea might have left. The damp "
    "sand squelches between your toes in your boots."
)
T17_LINE = "I hand her the coin, take the herring and eat it."
T17_DRAFT = (
    "Morning sunlight glints off the waves as the storm clouds loom overhead. You've made it to the North Docks of "
    "Saltmarrow. The air is cool and salty. Seagulls call overhead as they ride the currents above the harbour.\n\n"
    "You spot a fisherman, a woman with a grizzled look and a long knife at her belt. She eyes you up and down and "
    "says, \"Looks like you've got some trinkets, but nothing I can't get for myself. Your spoons are plain, and that "
    "buckle's been tarnished by the sea air. You're no stranger to this salt-stung coast, are you?\"\n\n"
    "You hand her a small coin from your pocket. \"Will you trade me a herring for this?\" you ask.\n\n"
    "She pockets the coin with a nod. \"Fair enough. Help yourself to a fish. There's plenty more where that came "
    "from.\" You take a glistening herring from the pile and pop it into your mouth. The taste of salt and ocean is "
    "strong on the fish as you eat.\n\n"
    "The fisherman watches you for a moment then asks, \"So what brings you to these docks so early? The harbour "
    "reeve has been looking for extra hands to unload the ships as they come in. A hard job, but there's coin in it. "
    "You look like you could use the work.\"\n\n"
    "The storm clouds seem to be gathering over the water as you consider her offer. You're not sure how long you "
    "can keep going like this, scavenging the coastline for scraps. A full belly and a little coin might be just "
    "what you need to turn your luck around..."
)
T11_LINE = "I ask Esme whether the guild has a contract I could run this tide to work the rest off."
T11_HEAD = (
    "Esme's lips press into a tight line. \"There's always work to be done, for those who are willing. But this tide "
    "is... tricky.\" She glances out a window at the swirling gray mist outside. \"The guild could use someone like "
    "you, though, to keep an eye on things. There's been talk of trouble in the north docks.\""
)
T11_TAIL = (
    "You feel a prickle of unease at the mention of the docks. \"What kind of trouble?\"\n\n"
    "Esme shakes her head. \"The usual. A few too many whispers in the shadows. The guild wants someone reliable to "
    "watch for anything... untoward. It's dangerous work, but it could go a long way towards settling what you "
    "owe.\"\n\n"
    "You nod slowly, considering. The guild's offer is tempting - a chance to pay off your debt and do something "
    "useful, all in one tide."
)

ORABEL = {"code": "E", "name": "Orabel", "role": "kitchen hand", "kind": "", "kind_number": 0, "died_turn": 0,
          "rank": "F", "stat_profile": {}, "location_id": 4}
WOLF = {"code": "F", "name": "Dire Wolf 1", "role": "dire wolf", "kind": "Dire Wolf", "kind_number": 1, "died_turn": 0,
        "rank": "F", "stat_profile": {}, "location_id": 4}


def _fresh_world():
    from app import db, rng, world

    db.init_db()
    rng.reset_seed_cache()
    world.start_playthrough({"player_name": "Isk Tarrow", "player_public_name": "Isk", "start_location": "Saltmarrow",
                             "special_ability_origin": "none"})


class _Asker:
    """The small asks, scripted: yes for the kinds given (as Hermes answered the wolf), no otherwise."""

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
            "SELECT id, code, name, role, attitude, race, kind, kind_number, location_id FROM npcs ORDER BY id"
        ).fetchall()]


def _here_id():
    from app import db

    with db.connect().closing() as conn:
        return int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])


# --- 1a. the creature is filed ----------------------------------------------


class TheWolfIsFiled(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_t22_the_dire_wolf_is_a_mention_named_by_the_prose(self):
        from app import unnamed

        wolf = [m for m in unnamed.mentions(T22_PROSE) if m["kind"] == "wolf"]
        self.assertEqual(len(wolf), 1)
        m = wolf[0]
        self.assertEqual((m["form"], m["phrase"], m["acts"], m["subject"]), ("the", "The dire wolf", True, True))
        # The player is in the sentence, not the clause; the prose met the wolf as new ("a dire wolf").
        self.assertFalse(m["you"])
        self.assertTrue(m["you_sentence"])
        self.assertEqual(m["full"], "dire wolf")
        self.assertEqual(unnamed.kind_title("dire wolf"), "Dire Wolf")
        self.assertEqual(unnamed.kind_head("Dire Wolf"), "wolf")
        self.assertIn("wolf", unnamed.shown_kinds(T22_PROSE))
        self.assertIn("dire wolf", unnamed.shown_kinds(T22_PROSE))

    def test_t22_files_dire_wolf_1_hostile_at_the_players_place(self):
        asker = _Asker(figures=("wolf",), hostile=("wolf",))
        _play(T22_PROSE, T22_LINE, asker)
        rows = [r for r in _rows() if r["kind"]]
        self.assertEqual([(r["name"], r["kind"], r["kind_number"], r["attitude"], r["race"]) for r in rows],
                         [("Dire Wolf 1", "Dire Wolf", 1, "hostile", "unknown")])
        self.assertEqual(rows[0]["location_id"], _here_id())
        self.assertEqual(len(asker.asked("figure_kind_check")), 1)
        self.assertIn('is "wolf" a being that can act on its own?', " ".join(asker.asked("figure_kind")))

    def test_t23_the_wolf_that_attacked_is_read_past_of_the(self):
        from app import unnamed

        # "any sign of the dire wolf that attacked": not "one of the ghouls".
        self.assertIn("wolf", unnamed.shown_kinds(T23_PROSE))
        self.assertEqual([m["kind"] for m in unnamed.mentions("One of the ghouls lunges at you.")], [])

    def test_the_wolf_is_the_dire_wolf_on_later_turns(self):
        asker = _Asker(figures=("wolf",), hostile=("wolf",))
        _play(T22_PROSE, T22_LINE, asker)
        _play("The dire wolf circles, its eyes glinting through the fog. It snarls and growls, circling closer.",
              T24_LINE, _Asker())
        self.assertEqual([r["name"] for r in _rows() if r["kind"]], ["Dire Wolf 1"])
        _play("The wolf lunges at you again.", "i brace", _Asker())
        self.assertEqual([r["name"] for r in _rows() if r["kind"]], ["Dire Wolf 1"])


class SeagullsAreNoPerson(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_t14_a_plural_with_its_plural_verb_is_no_named_speaker(self):
        from app import world

        self.assertEqual(world._figure_hints(T14_PROSE, ["Osbert Woodall", "Mira", "Esme Pollard"]), [])
        # A name keeps the singular verb.
        self.assertEqual(world._figure_hints("Mara calls out from the quay."), ["Mara calls"])

    def test_t14_files_no_row_for_the_birds(self):
        before = len(_rows())
        asker = _Asker()
        _play(T14_PROSE, T14_LINE, asker)
        self.assertEqual([r["name"] for r in _rows()[before:]], [])
        self.assertNotIn("Seagulls", [r["name"] for r in _rows()])
        # The scenery plural the player does not act on is not asked about either.
        self.assertNotIn("seagull", " ".join(asker.asked("figure_kind")))


# --- 1b. whom the blow is at ---------------------------------------------------


class WhomTheBlowIsAt(unittest.TestCase):
    def test_object_nouns_read_past_a_participle_and_a_possessive(self):
        from app import attack_intent as A

        self.assertEqual(A.object_nouns(T24_LINE), ["wolf", "fog"])
        self.assertEqual(A.object_nouns(T23_LINE), ["wolf"])
        self.assertEqual(A.object_nouns("i shoot the old building"), ["building"])
        self.assertEqual(A.object_nouns("i shoot the ghoul lunging at you"), ["ghoul"])

    def test_the_blow_is_one_act_of_the_line(self):
        from app import attack_intent as A

        self.assertEqual(A.attack_clauses(T24_LINE), ["slash at the dire wolf circling us in the fog"])
        self.assertEqual(A.attack_clauses(T23_LINE), ["stab at the dire wolf's throat as it comes in"])
        self.assertEqual(A.attack_clauses("i shoot the ghoul and then the raider"), ["i shoot the ghoul"])
        # One act, or none the tables know: the whole line.
        self.assertEqual(A.attack_clauses("i snap her neck and then burn the clinic to the ground"), [])
        self.assertEqual(A.attack_clauses("i shoot the bastard"), [])

    def test_t24_ignore_orabel_never_aims_at_orabel(self):
        from app import attack_intent as A

        self.assertFalse(A.line_may_target(T24_LINE, ORABEL, people=[ORABEL]))
        self.assertFalse(A.line_may_target(T24_LINE, ORABEL, people=[ORABEL], shown={"wolf"}))
        self.assertFalse(A.line_may_target("I shout at @E to get back, then stab at the dire wolf's neck", ORABEL, people=[ORABEL]))
        self.assertFalse(A.line_may_target("I ignore her and slash at the wolf", ORABEL, people=[ORABEL]))
        # Named in the blow itself: aimed.
        self.assertTrue(A.line_may_target("I ignore the wolf and stab Orabel", ORABEL, people=[ORABEL]))
        self.assertTrue(A.line_may_target("i stab her", ORABEL, people=[ORABEL]))
        # The wolf's own row is meant by its head noun and by its two words.
        self.assertTrue(A.line_may_target(T24_LINE, WOLF, people=[ORABEL, WOLF]))
        self.assertTrue(A.line_may_target("i stab the wolf", WOLF, people=[ORABEL, WOLF]))
        self.assertEqual([p["code"] for p in A.kind_figures(T23_LINE, [ORABEL, WOLF])], ["F"])

    def test_t23_a_creature_the_prose_showed_is_positive_evidence(self):
        from app import attack_intent as A

        shown = A.shown_kinds(T22_PROSE)
        self.assertFalse(A.line_may_target(T23_LINE, ORABEL, people=[ORABEL], shown=shown))
        self.assertEqual(A.unknown_creature(T23_LINE, [ORABEL], shown), "wolf")
        # With no prose showing a wolf, the old rule stands: a noun the engine knows nothing about is no
        # evidence ("the bastard" goes to the one person present).
        self.assertTrue(A.line_may_target(T23_LINE, ORABEL, people=[ORABEL], shown=set()))
        self.assertTrue(A.line_may_target("i shoot the bastard", ORABEL, people=[ORABEL], shown=shown))
        # A person word the prose shows is someone here, never a creature to mint.
        self.assertNotIn("stranger", A.shown_kinds(T23_PROSE))
        self.assertEqual(A.unknown_creature("i hit the stranger", [ORABEL], A.shown_kinds(T23_PROSE)), "")

    def test_decide_mints_the_shown_creature_and_aims_at_it_else_leaves_the_roll_untargeted(self):
        from app import attack_intent as A

        ctx = {"current_location": {"code": "L4", "npcs": [ORABEL]}, "npcs": [ORABEL], "last_narration": T22_PROSE}
        minted = []

        def minter(kind):
            minted.append(kind)
            return WOLF

        for line in (T23_LINE, T24_LINE):
            inferred = {"skill_code": "melee", "npc_ref": {"code": "E", "name": "Orabel"}, "opposition": {"name": "Orabel"},
                        "weapon_or_tool": ""}
            check, report = A.decide(f"Player: {line}", ctx, inferred, None, minter=minter)
            self.assertEqual(report.get("not_the_lines", {}).get("code"), "E", line)
            self.assertEqual(report.get("unknown_noun"), "wolf", line)
            self.assertEqual((report.get("from"), check and check["attack"]["code"]), ("minted", "F"), line)
            self.assertTrue(check.get("replaces_inferred"))
            self.assertIsNone(inferred.get("npc_ref"))
        self.assertEqual(minted, ["wolf", "wolf"])
        # No minter (a stub turn): the roll stands with no target, and nothing is aimed at Orabel.
        inferred = {"skill_code": "melee", "npc_ref": {"code": "E", "name": "Orabel"}, "opposition": {"name": "Orabel"}}
        check, report = A.decide(f"Player: {T24_LINE}", ctx, inferred, None)
        self.assertIsNone(check)
        self.assertIsNone(report.get("target"))
        self.assertEqual(report.get("unknown_noun"), "wolf")
        self.assertIsNone(inferred.get("attack"))

    def test_mint_shown_files_the_wolf_from_the_last_turns_prose(self):
        from app import db, entity_kinds, unnamed

        _fresh_world()
        asker = _Asker(figures=("wolf",), hostile=("wolf",))
        previous = entity_kinds.set_kind_ask(asker)
        try:
            with db.connect().closing() as conn:
                shell = unnamed.mint_shown(conn, T22_PROSE, "wolf", _here_id(), call=entity_kinds._call, line=T23_LINE)
                conn.commit()
        finally:
            entity_kinds.set_kind_ask(previous)
        self.assertEqual((shell["name"], shell["kind"], shell["attitude"]), ("Dire Wolf 1", "Dire Wolf", "hostile"))
        self.assertEqual([r["name"] for r in _rows() if r["kind"]], ["Dire Wolf 1"])
        # The prose names it once and the player's line again: still the dire wolf.
        with db.connect().closing() as conn:
            conn.execute("DELETE FROM npcs WHERE kind = 'Dire Wolf'")
            conn.commit()
        previous = entity_kinds.set_kind_ask(asker)
        try:
            with db.connect().closing() as conn:
                shell = unnamed.mint_shown(conn, T23_PROSE, "wolf", _here_id(), call=entity_kinds._call, line=T24_LINE)
                conn.commit()
        finally:
            entity_kinds.set_kind_ask(previous)
        self.assertEqual(shell["name"], "Dire Wolf 1")
        # A person word is the figure hints' own, never minted here.
        with db.connect().closing() as conn:
            self.assertIsNone(unnamed.mint_shown(conn, T23_PROSE, "stranger", _here_id(), call=entity_kinds._call))

    def test_the_engine_line_names_the_wolf_not_the_bystander(self):
        from app import interpreter as I

        people = [{**ORABEL, "health": 21, "max_health": 21}, {**WOLF, "health": 21, "max_health": 21}]
        match = I.Matcher(people, [])
        check = {"skill": {"code": "melee", "name": "Melee", "category": "combat"}, "natural": 20, "total": 24,
                 "outcome": "critical_success", "attack": {"code": "E", "name": "Orabel"}}
        records = {"player_line": T24_LINE, "here_id": 4, "shown_kinds": ["wolf"]}
        row = I.attacked_row(check, records, match)
        self.assertEqual(row["code"], "F")
        self.assertEqual(I.called(row, prose=True), "the dire wolf")
        # Without the wolf's row and with the prose showing it: no one is the target, no line names Orabel.
        match = I.Matcher([{**ORABEL, "health": 21, "max_health": 21}], [])
        self.assertIsNone(I.attacked_row(check, records, match))


# --- 2. the gate keeps the player's own act -------------------------------------


def _asks(answers: dict[str, str]):
    from app.player_agency import AgencyAsks

    return AgencyAsks(lambda system, user, phase: answers.get(phase.rsplit("_", 1)[-1], "no"))


def _gate(draft: str, line: str):
    from app import llm
    from app.turn_dsl import parse_dsl_turn

    turn = parse_dsl_turn(f"===NAR===\n{draft}\n\n===OPS===\nSUMMARY: \"A scene.\"\n", line)
    return llm._drop_player_overreach(turn, line, "test", None, None, _asks({"reply": "yes", "voices": "yes"}))


class TheAskedActStays(unittest.TestCase):
    def test_the_lines_verbs(self):
        from app.llm import player_verbs

        self.assertEqual(player_verbs(T17_LINE), {"hand", "take", "eat"})
        self.assertEqual(player_verbs(T24_LINE), {"ignor", "slash"})
        self.assertEqual(player_verbs('"Morning," I say, and walk to the quay.'), {"walk"})

    def test_t17_the_purchase_sentences_are_kept(self):
        turn = _gate(T17_DRAFT, T17_LINE)
        text = turn["narration"]
        self.assertIn("She pockets the coin with a nod.", text)
        self.assertIn("You take a glistening herring from the pile and pop it into your mouth.", text)
        self.assertIn("The taste of salt and ocean is strong on the fish as you eat.", text)
        cut = turn.get("_scene_cut") or {}
        self.assertEqual(cut.get("family"), "reply_to_dropped_act")

    def test_t24_the_slash_and_the_wolfs_answer_are_kept_and_the_second_round_is_not(self):
        turn = _gate(T24_DRAFT, T24_LINE)
        text = turn["narration"]
        self.assertIn("With a roar, you slash at the wolf, aiming for its throat.", text)
        self.assertIn("The wolf howls in pain and rage, turning to face you.", text)
        self.assertNotIn("You sidestep and slash again", text)
        self.assertNotIn("You dance around each other", text)

    def test_the_cut_moves_only_for_the_lines_own_verbs(self):
        from app.llm import asked_act_cut

        text = ('"What kind?" the smith asks. "A longsword," you say. He hands you a longsword. You take it and '
                "walk out.")
        cut = text.index('"A longsword,"')
        # The line asked for a sword, not to take one or walk out: nothing moves.
        self.assertEqual(asked_act_cut(text, cut, "I ask the smith for a sword"), (cut, ""))
        moved, kept = asked_act_cut(text, cut, "I ask the smith for a sword and take it")
        self.assertEqual(kept, "You take it and walk out.")
        self.assertEqual(moved, len(text))

    def test_t11_a_quest_the_line_asked_for_stays_with_a_cut_tail(self):
        from app.llm import _drop_ops_of_cut_tail
        from app.quest_parser import player_asks_for_work

        self.assertTrue(player_asks_for_work(T11_LINE))
        mark = {"op": "QUEST", "title": "title: Watch the North Docks step: Watch for anything untoward at the north dock",
                "giver": "", "step": "", "location": "", "reward": "", "evidence": ""}
        turn = {"narration": T11_HEAD, "quest_marks": [dict(mark)], "_dsl": {}}
        dropped = _drop_ops_of_cut_tail(turn, T11_HEAD, T11_TAIL, T11_LINE)
        self.assertEqual(dropped, [])
        self.assertEqual(turn["quest_marks"], [mark])
        # A line that asked for no work: the op the tail alone supported still goes.
        turn = {"narration": T11_HEAD, "quest_marks": [dict(mark)], "_dsl": {}}
        dropped = _drop_ops_of_cut_tail(turn, T11_HEAD, T11_TAIL, "I ask Esme how her day has been.")
        self.assertEqual(len(dropped), 1)
        self.assertEqual(turn["quest_marks"], [])


class TheEatenHerringIsNoRefusedGain(unittest.TestCase):
    def setUp(self):
        _fresh_world()

    def test_t17_the_take_and_eat_sentence_stays_in_the_prose(self):
        prose = (
            "You hand her a small coin from your pocket. She pockets the coin with a nod. \"Fair enough. Help yourself "
            "to a fish.\" You take a glistening herring from the pile and pop it into your mouth. The taste of salt and "
            "ocean is strong on the fish as you eat."
        )
        turn = _play(prose, T17_LINE, _Asker(), ops='SUMMARY: "A herring."\nGRANT: herring')
        self.assertIn("You take a glistening herring from the pile and pop it into your mouth.", turn["narration"])
        from app import db

        with db.connect().closing() as conn:
            names = [r[0] for r in conn.execute("SELECT name FROM inventory WHERE quantity > 0").fetchall()]
        self.assertNotIn("herring", [n.lower() for n in names])


if __name__ == "__main__":
    unittest.main()
