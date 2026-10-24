"""stage1 (Hermes 3 8B, Sonnet as the player, 2026-10-25): a creature an op named was filed as a person, and blows at it ran no attack machinery.

The recorded turns (run folder stage1, traces turn-95262bc5-0000NN-player.json, NN = T + 1):

- T11: "I step into the lair and look around for the creature that lives here." The draft's NPC_NEW named
  "Serpent of Saltmarrow". The person-or-place ask had no sentence naming it ("Text: " was empty) and replied
  "A place." (ledger kind_unread), so the row was filed as a named person with no kind and race human. The
  sentence that showed the serpent ("The shadowy form of a large serpent emerges ... as it rears up to regard
  you ...") was cut as a follow-on of the refused silver amulet (refused_gain_follow_on_trimmed), so the scene
  never held the serpent (conversation present []).
- T12: "I swing my fist at the creature as it comes out of the dark." melee 1d20=3, failure, unskilled
  mishap (-1 health, "your own side"). No one was in the scene record, so attack_intent.decide had no one to
  ask about, returned no asks, and world._attack_check_for_line noted nothing; the trigger's check had no
  target, show_attacks had no row, so no engine line: the draft's "Your fist connects with the creature's
  snout" stood and the -1 health was never shown.
- T13: "I swing at the creature again, going for its eyes, and shout at it to back off." melee 3 again; the
  line's noun phrase read "the creature again" with head "again"; the draft's "as your blow connects" stood.

The prose, lines and rows below are the run's own, verbatim.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-stage1-creature-"))
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

T11_LINE = "I step into the lair and look around for the creature that lives here."
T11_DRAFT = (
    "You step cautiously into the shadowy lair, the flickering torchlight casting eerie patterns on the damp stone "
    "walls. The musty scent of earth and the faint skittering of small creatures in the dark surround you. You strain "
    "your eyes to pierce the gloom, searching for some sign of the creature that makes this dank den its home.\n\n"
    "Your gaze settles on a glint of metal half-buried in the loamy floor. You stoop to retrieve it, discovering a "
    "tarnished silver amulet bearing an odd sigil – a twisting branch with leaves of deep emerald. The intricate "
    "design seems to hold some arcane power, humming faintly as you turn it in your fingers.\n\n"
    "A sudden rustling from deeper within the lair makes you freeze. You hold your breath, listening intently. The "
    "sound grows closer, a slow shuffling step, punctuated by the brush of scales on stone. Your heart quickens as "
    "you wait, the silver amulet gripped tightly in your hand. The shadowy form of a large serpent emerges from the "
    "darkness, its yellow eyes glinting with malevolent intelligence as it rears up to regard you with primal malice."
)
SERPENT_SENTENCE = (
    "The shadowy form of a large serpent emerges from the darkness, its yellow eyes glinting with malevolent "
    "intelligence as it rears up to regard you with primal malice."
)
# The op as the DSL parsed it (final_turn.npcs[0]).
T11_OP = {"code": None, "name": "Serpent of Saltmarrow", "race": "human", "location": "L6", "role": "lair inhabitant",
          "summary": "", "attitude": "neutral", "_bound_hint": "the shadowy lair"}

T12_LINE = "I swing my fist at the creature as it comes out of the dark."
T12_PRIOR = (  # T12's last_narration: T11's prose as the run left it
    "You step cautiously into the shadowy lair, the flickering torchlight casting eerie patterns on the damp stone "
    "walls. The musty scent of earth and the faint skittering of small creatures in the dark surround you. You strain "
    "your eyes to pierce the gloom, searching for some sign of the creature that makes this dank den its home.\n\n"
    "Your gaze settles on a glint of metal half-buried in the loamy floor.\n\n"
    "A sudden rustling from deeper within the lair makes you freeze. You hold your breath, listening intently. The "
    "sound grows closer, a slow shuffling step, punctuated by the brush of scales on stone."
)
T12_DRAFT = (
    "You swing your fist at the creature emerging from the shadows. Your fist connects with the creature's snout "
    "with a satisfying thud. The creature howls in pain and staggers back into the darkness. You stand panting, your "
    "arm aching from the impact."
)
T13_LINE = "I swing at the creature again, going for its eyes, and shout at it to back off."
# T13's draft after the unowned club sentence was dropped (unowned_weapon_dropped), its first paragraph.
T13_DRAFT = (
    "The creature rears back, snarling and hissing, as your blow connects and it recoils. You shout at it to back "
    "off, waving your weapon threateningly.\n\n"
    "The creature, still snarling, lowers its head and bares its fangs but does not advance further."
)


def _check(limb: str, attack: dict | None) -> dict:
    """final_turn.skill_checks[0] of T12 (limb side) / T13 (limb ribs), the fields the engine reads."""
    return {
        "enabled": True, "skill": {"code": "melee", "name": "Melee", "category": "combat", "attribute": "strength"},
        "dice": "d20", "natural": 3, "base": 10, "modifier": 0, "total": 3, "dc": 11, "outcome": "failure",
        "degree": "unskilled_mishap", "margin": -8, "unskilled": True, "mishap": True, "opposition": None,
        "injury": {"kind": "self_injury", "limb": limb, "severity": False, "lasting": False, "health_delta": -1,
                   "summary": f"Unskilled with Melee: you injure your own {limb}.", "combat_penalty": {}},
        "weapon_or_tool": "", "attack": attack,
    }


# The row as the run filed it (T12 prompt_context.locations[0].npcs[0]), and as the fix files it.
SERPENT_UNREAD = {"id": 5, "code": "E", "location_id": 6, "name": "Serpent of Saltmarrow", "race": "human",
                  "role": "lair inhabitant", "attitude": "neutral", "rank": "F", "health": 0, "max_health": 0,
                  "attack_min": 0, "attack_max": 0, "defense": 0, "dodge": 0, "died_turn": 0, "dead": 0,
                  "kind": "", "kind_number": 0, "sketch_turn": 12}
SERPENT = {**SERPENT_UNREAD, "kind": "Serpent", "race": "unknown", "health": 21, "max_health": 21,
           "attack_min": 2, "attack_max": 6, "defense": 3, "dodge": 3}


def _context(row: dict, present: list[str] | None = None, prior: str = T12_PRIOR) -> dict:
    """T12's prompt_context, the parts the attack reader reads: the lair, its one row, the scene record."""
    place = {"id": 6, "code": "L6", "name": "The Deep Marsh", "npcs": [copy.deepcopy(row)]}
    return {
        "current_location": {"id": 6, "code": "L6", "name": "The Deep Marsh"},
        "locations": [place],
        "conversation_turn": {"addressed": [], "present": list(present or []), "listening": [],
                              "names": {"E": row["name"]}},
        "last_narration": prior,
        "dead": [],
    }


def _inferred() -> dict:
    """infer_check_from_action's melee for the line: no one to aim at (the run's dice row had no opposition)."""
    return {"skill_code": "melee", "opposition": None, "npc_ref": None, "social": False}


class Notes:
    """Collects turn_ledger notes."""

    def __init__(self):
        self.rows: list[dict] = []

    def __call__(self, area, decision, **detail):
        self.rows.append({"area": area, "decision": decision, **detail})

    def named(self, decision: str) -> list[dict]:
        return [r for r in self.rows if r["decision"] == decision]


def _no_attack_ask(phase, prompt, max_tokens):
    raise AssertionError(f"no attack ask is needed: {phase}")


# --- T11: the serpent the op named is a creature ------------------------------


class T11TheOpNamedCreatureIsACreature(unittest.TestCase):

    def test_the_head_noun_the_prose_shows_acting_is_its_kind(self):
        from app import unnamed

        read = unnamed.op_creature_kind("Serpent of Saltmarrow", T11_DRAFT)
        self.assertIsNotNone(read)
        self.assertEqual(read["kind"], "Serpent")
        self.assertEqual(read["phrase"], "a large serpent")
        self.assertEqual(read["sentence"], SERPENT_SENTENCE)

    def test_a_person_named_the_same_way_is_no_creature(self):
        from app import unnamed

        # A job, a title, a person word, he / she, a name the prose never uses as a common noun.
        self.assertIsNone(unnamed.op_creature_kind(
            "Warden of the Marsh", "The warden steps out of the hut and eyes you, his hand on his blade."))
        self.assertIsNone(unnamed.op_creature_kind("King of Saltmarrow", "The king rises from his throne."))
        self.assertIsNone(unnamed.op_creature_kind("Old Grey", "A grey wolf lopes out of the reeds, its hackles up."))
        self.assertIsNone(unnamed.op_creature_kind("Mira Vale", "Mira Vale waves and calls you over."))

    def test_settle_kinds_marks_it_hostile_and_asks_no_person_or_place(self):
        from app import entity_kinds
        from app.db import init_db

        init_db()
        phases: list[str] = []

        def ask(system, user, *, trace=None, usage=None, phase="", max_tokens=None):
            phases.append(phase)
            if phase == entity_kinds.KIND_PHASE:
                return "A place."  # the run's reply
            if phase == "figure_hostile":
                return "Yes" if '"a large serpent"' in user and SERPENT_SENTENCE in user else "No"
            return "No"

        result = {"narration": T11_DRAFT, "npcs": [copy.deepcopy(T11_OP)]}
        notes = Notes()
        previous = entity_kinds.set_kind_ask(ask)
        try:
            with mock.patch("app.turn_ledger.note", notes):
                entity_kinds.settle_kinds(result, T11_LINE)
        finally:
            entity_kinds.set_kind_ask(previous)
        npc = result["npcs"][0]
        self.assertEqual(npc.get("_creature_kind"), "Serpent")
        self.assertTrue(npc.get("_creature_hostile"))
        self.assertNotIn(entity_kinds.KIND_PHASE, phases)  # the empty-text person-or-place ask is not made
        self.assertEqual(notes.named("kind_unread"), [])
        self.assertEqual(len(notes.named("op_name_is_a_creature")), 1)

    def test_the_row_is_filed_with_its_kind_hostile_in_the_scene_with_health(self):
        from app import unnamed
        from app.db import connect, init_db

        init_db()
        with connect().closing() as conn:
            conn.execute("INSERT OR IGNORE INTO locations (id, code, name) VALUES (6, 'L6', 'The Deep Marsh')")
            cur = conn.execute(
                "INSERT INTO npcs (code, location_id, name, race, role, attitude) VALUES "
                "('E', 6, 'Serpent of Saltmarrow', 'human', 'lair inhabitant', 'neutral')")
            row_id = int(cur.lastrowid)
            npc = {**T11_OP, "_creature_kind": "Serpent", "_creature_hostile": True}
            result: dict = {}
            with mock.patch("app.turn_ledger.note", Notes()):
                self.assertTrue(unnamed.file_op_creature(conn, npc, row_id, result))
            row = conn.execute("SELECT * FROM npcs WHERE id = ?", (row_id,)).fetchone()
            self.assertEqual(row["name"], "Serpent of Saltmarrow")
            self.assertEqual(row["kind"], "Serpent")
            self.assertEqual(row["attitude"], "hostile")
            self.assertEqual(row["race"], "unknown")
            self.assertGreater(int(row["max_health"] or 0), 0)
            self.assertIn("E", result["scene_cast"]["present"])
            conn.execute("DELETE FROM npcs WHERE id = ?", (row_id,))

    def test_the_serpent_is_the_creature_the_beast_and_the_serpent(self):
        from app.attack_intent import _kinds_of

        self.assertTrue({"serpent", "creature", "beast", "animal"} <= _kinds_of(SERPENT))
        self.assertEqual(_kinds_of(SERPENT_UNREAD), set())


class T11TheSerpentSentenceSurvivesTheAmuletTrim(unittest.TestCase):

    def test_only_the_amulets_sentences_go(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk Tarrow", "start_location": "Saltmarrow",
                                 "special_ability_origin": "none"})
        result = {"narration": T11_DRAFT,
                  "narration_segments": [{"label": "paragraph", "text": p} for p in T11_DRAFT.split("\n\n")]}
        notes = Notes()
        with connect().closing() as conn, mock.patch("app.turn_ledger.note", notes):
            world._reconcile_prose_with_state(
                conn, result,
                rejected=[{"name": "silver amulet", "tokens": ["silver", "amulet"], "outcome": "gain",
                           "taken_unasked": True}],
                movement_report={}, gold_note=None, purse_note=None, player_input=T11_LINE,
            )
        text = world._narration_text(result)
        self.assertIn(SERPENT_SENTENCE, text)
        self.assertNotIn("amulet", text)
        self.assertNotIn("The intricate design", text)
        kept = notes.named("refused_gain_follow_on_kept")
        self.assertEqual(len(kept), 1)
        self.assertTrue(SERPENT_SENTENCE.startswith(kept[0]["sentence"]))

    def test_the_pronoun_reading(self):
        from app.world import _pronoun_is_subjects

        self.assertTrue(_pronoun_is_subjects(SERPENT_SENTENCE))
        for sentence in ("You pull it free and wipe the grime off.", "It's a small piece, but it might be useful.",
                         "The merchant smiles as you pocket it.", "A moment later it slips from your fingers.",
                         "The old man nods and hands it over."):
            self.assertFalse(_pronoun_is_subjects(sentence), sentence)


# --- T12 / T13: the blow finds the serpent ---------------------------------------


class T12TheBlowFindsTheSerpent(unittest.TestCase):

    def test_the_creature_is_the_serpent_no_one_in_the_scene_record(self):
        from app import attack_intent

        inferred = _inferred()
        check, report = attack_intent.decide(T12_LINE, _context(SERPENT, present=[]), inferred, _no_attack_ask)
        self.assertIsNotNone(check)
        self.assertEqual(check["attack"]["code"], "E")
        self.assertEqual(report["from"], "kind")
        self.assertEqual(report["from_place"], ["E"])

    def test_with_the_serpent_in_the_scene(self):
        from app import attack_intent

        check, report = attack_intent.decide(T12_LINE, _context(SERPENT, present=["E"]), _inferred(), _no_attack_ask)
        self.assertEqual((check or {}).get("attack", {}).get("code"), "E")
        self.assertNotIn("from_place", report)

    def test_t13_the_creature_again(self):
        from app import attack_intent

        self.assertIn("creature", attack_intent.object_nouns(T13_LINE))
        check, _report = attack_intent.decide(T13_LINE, _context(SERPENT, present=["E"]), _inferred(), _no_attack_ask)
        self.assertEqual((check or {}).get("attack", {}).get("code"), "E")

    def test_a_kind_unread_row_is_found_by_its_names_head_noun(self):
        from app import attack_intent

        line = "I swing my fist at the serpent as it comes out of the dark."
        asked: list[str] = []

        def ask(phase, prompt, max_tokens):
            asked.append(phase)
            return "Yes" if phase == attack_intent.PHASE_ATTACK else "No"

        check, report = attack_intent.decide(line, _context(SERPENT_UNREAD, present=[]), _inferred(), ask)
        self.assertEqual(report.get("from_place"), ["E"])
        self.assertEqual((check or {}).get("attack", {}).get("code"), "E")

    def test_the_run_as_it_was_now_notes_the_blow(self):
        """The row as the run filed it (no kind, no one in the scene): no target, but the roll is noted."""
        from app import world

        notes = Notes()
        with mock.patch("app.turn_ledger.note", notes):
            check = world._attack_check_for_line(T12_LINE, _context(SERPENT_UNREAD, present=[]), _inferred(), [], [],
                                                 ask=_no_attack_ask)
        self.assertIsNone(check)
        self.assertEqual(notes.named("attack_target_unknown_noun")[0]["noun"], "creature")
        self.assertEqual(len(notes.named("attack_not_found")), 1)


class T12TheEngineWritesTheMiss(unittest.TestCase):

    def _show(self, text: str, check: dict, people: list[dict], line: str):
        from app import interpreter as I

        records = {"people": people, "places": [], "player_names": ["Isk Tarrow", "Isk"], "here_id": 6,
                   "player_line": line, "player_quotes": []}
        report: dict = {}
        notes = Notes()
        with mock.patch("app.turn_ledger.note", notes):
            out = I.show_attacks(text, {"skill_checks": [check]}, I.Matcher(people, []), report, records)
        return out, report, notes

    def test_the_hit_the_draft_wrote_gets_the_engines_miss_after_it(self):
        out, report, _notes = self._show(T12_DRAFT, _check("side", {"code": "E", "name": "Serpent of Saltmarrow"}),
                                         [SERPENT], T12_LINE)
        beat = report["attack_beats"][0]
        self.assertEqual(beat["state"], "contradicted")
        self.assertIn("misses Serpent of Saltmarrow [[E]]", beat["beat"])
        self.assertTrue(beat["beat"].endswith("your own side takes the hurt."))
        # Nothing of the draft is dropped; the line follows the passage that shows the hit.
        for sentence in T12_DRAFT.split(". "):
            self.assertIn(sentence.rstrip("."), out)
        self.assertLess(out.index("staggers back into the darkness."), out.index(beat["beat"]))

    def test_t13_as_your_blow_connects_is_the_hit_contradicted(self):
        out, report, _notes = self._show(T13_DRAFT, _check("ribs", {"code": "E", "name": "Serpent of Saltmarrow"}),
                                         [SERPENT], T13_LINE)
        beat = report["attack_beats"][0]
        self.assertEqual(beat["state"], "contradicted")
        self.assertIn("your own ribs take the hurt.", beat["beat"])
        self.assertIn("as your blow connects and it recoils", out)

    def test_no_row_at_all_the_miss_names_the_creature(self):
        out, report, notes = self._show(T12_DRAFT, _check("side", None), [], T12_LINE)
        beat = report["attack_beats"][0]
        self.assertEqual(beat["noun"], "creature")
        from app import attack_line

        self.assertIn(" the creature;", beat["beat"])  # "Your fist falls short of the creature; you jar your own side."
        self.assertEqual(attack_line.outcome_of(beat["beat"]), attack_line.MISS)
        self.assertIn("your own side", beat["beat"])
        self.assertIn(beat["beat"], out)
        self.assertEqual(len(notes.named("attack_contradiction_line_added")), 1)

    def test_no_row_and_a_draft_that_says_nothing_against_the_roll_gets_no_line(self):
        draft = "You swing your fist at the creature emerging from the shadows. You stand panting in the dark."
        out, report, notes = self._show(draft, _check("side", None), [], T12_LINE)
        self.assertEqual(out, draft)
        self.assertNotIn("attack_beats", report)
        self.assertEqual(notes.named("attack_untargeted_no_line")[0]["why"], "draft unshown")

    def test_no_row_and_a_hit_writes_no_hit(self):
        hit = {**_check("side", None), "natural": 17, "total": 17, "outcome": "success", "degree": "success",
               "mishap": False, "injury": None}
        out, report, notes = self._show(T12_DRAFT, hit, [], T12_LINE)
        self.assertEqual(out, T12_DRAFT)
        self.assertNotIn("attack_beats", report)
        self.assertEqual(notes.named("attack_untargeted_no_line")[0]["noun"], "creature")


class T12TheBlowHasItsFight(unittest.TestCase):
    """'swing ... at' is no combat for the intent reader, yet the roll is aimed: the fight is built for its target."""

    def test_the_aimed_miss_is_resolved_on_the_serpent(self):
        from app import world
        from app.db import init_db

        init_db()
        state = {"settings": {}, "player": {"stats": {"strength": 7}}, "inventory": [], **_context(SERPENT, ["E"])}
        checks = [_check("side", {"code": "E", "name": "Serpent of Saltmarrow"})]
        with mock.patch("app.turn_ledger.note", Notes()):
            combat = world._combat_for_aimed_check(state, T12_LINE, {"status": "not_combat"}, checks)
            self.assertIsNotNone(combat)
            self.assertEqual(combat["status"], "resolved_player_attack")
            self.assertEqual(combat["target"]["code"], "E")
            followed = world._combat_follows_attack_check(combat, checks) or combat
        self.assertEqual(followed["resolution"]["outcome"], "miss")
        self.assertEqual(followed["resolution"]["damage"], 0)

    def test_a_built_fight_is_not_rebuilt(self):
        from app import world

        checks = [_check("side", {"code": "E", "name": "Serpent of Saltmarrow"})]
        self.assertIsNone(world._combat_for_aimed_check({}, T12_LINE, {"status": "resolved_player_attack"}, checks))
        self.assertIsNone(world._combat_for_aimed_check({}, T12_LINE, {"status": "not_combat"}, [_check("side", None)]))


if __name__ == "__main__":
    unittest.main()
