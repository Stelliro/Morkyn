"""8B run 150: faults fixed by class from T34 to T46.

T34: "Rafe ... watches from the corner. He's a man who speaks with actions,
not promises" seeded a drawn "Eadric Joliffe, eel trapper" for "a man".
T36: "I pick the crustacean back up" rolled lockpicking and made the owned
crab x2 on prose that only held it.
T37, T40: "I'll tell you if I'll do it" and "before I agree to anything" took
the job; Rafe's scroll errand was filed under his crab job.
T46: "You're doing good work ... the guild needs more hands, and you're
helping out" filed "Helping Out at the Guild".

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run150
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-run150-"))
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


def _pack(*names):
    from app.db import connect, init_db

    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM inventory")
        for i, (name, qty) in enumerate(names):
            conn.execute("INSERT INTO inventory (code, name, quantity) VALUES (?, ?, ?)", (f"I{i + 1}", name, qty))


def _filter(changes, narration, line):
    from app import world
    from app.db import connect

    rejected: list = []
    with connect() as conn:
        kept = world._filter_inventory_changes(conn, changes, narration=narration, player_input=line, rejected=rejected)
    return kept, rejected


class PickingAThingUpIsNoLock(unittest.TestCase):
    def test_pick_back_up_rolls_nothing(self):
        from app.skill_checks import infer_check_from_action

        check = infer_check_from_action(
            "\"Then name it, Rafe. What does the reeve want from me?\" I pick the crustacean back up and wait for a straight answer."
        )
        self.assertFalse(check and check.get("skill_code") == "lockpicking", check)

    def test_picking_the_lock_still_rolls(self):
        from app.skill_checks import infer_check_from_action

        self.assertEqual((infer_check_from_action("I pick the lock on the chest.") or {}).get("skill_code"), "lockpicking")


class OwnThingPickedBackUp(unittest.TestCase):
    LINE = "\"Then name it, Rafe. What does the reeve want from me?\" I pick the crustacean back up and wait for a straight answer."
    PROSE = ("Rafe's jaw tightened as he stared at the crustacean in your hands. You held the crustacean tighter, the shell "
             "cool beneath your fingertips. “The reeve wants more than a name,” he said.")

    def test_the_crab_stays_one_crab(self):
        _pack(("crustacean", 1))
        kept, rejected = _filter([{"name": "crustacean", "quantity_delta": 1}], self.PROSE, self.LINE)
        self.assertEqual(kept, [], rejected)


class AFigureWhoIsTheManJustNamed(unittest.TestCase):
    PROSE = ("You leave the coins where they lie and ask Mabel what the other choice is. Rafe, the harbour reeve, watches "
             "from the corner of his office, his expression unreadable. He’s a man who speaks with actions, not promises, "
             "and his presence adds a subtle pressure to the moment.")

    def test_no_new_person_is_seeded_for_the_man(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        with connect() as conn:
            conn.execute("DELETE FROM npcs")
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('A', 1, 'Mabel', 'tally clerk')")
            conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('B', 1, 'Rafe', 'harbour reeve')")
            seeded = world._ensure_npcs_from_narration(conn, {"npcs": []}, self.PROSE, 1)
            names = [str(n.get("name") or "") for n in seeded if isinstance(n, dict)]
        self.assertEqual(names, [], seeded)


class AConditionalYesIsNoYes(unittest.TestCase):
    LINES = [
        "\"A favor, then. Say what it is and I'll tell you if I'll do it.\" I put the crustacean back in my pack and listen.",
        "\"What does loading pay, and whose ship is it?\" I ask Rafe before I agree to anything.",
    ]

    def test_typed_accept_waits(self):
        from app.local_intel import typed_accept
        from app.quest_parser import player_accepts

        for line in self.LINES:
            self.assertFalse(typed_accept(line), line)
            self.assertFalse(player_accepts(line), line)

    def test_a_plain_yes_still_takes_it(self):
        from app.local_intel import typed_accept

        self.assertTrue(typed_accept("\"Cargo first. I'll do it.\" I roll up my sleeves."))


class AJobAboutAnotherThing(unittest.TestCase):
    def test_scroll_is_not_the_crab(self):
        from app.quest_parser import _same_job_subject

        self.assertFalse(_same_job_subject("Fetch a Scroll from the Reeve's Office", "Fetch the Crab from the Reeve"))
        self.assertFalse(_same_job_subject("Coral Wreck Salvage", "Loading the Cargo Crates"))

    def test_the_same_thing_reworded_is_the_same_job(self):
        from app.quest_parser import _same_job_subject

        self.assertTrue(_same_job_subject("Bring the Crab to the Reeve", "Fetch the Crab from the Reeve"))
        self.assertTrue(_same_job_subject("Salvage Job", "Clear the Wreck"))


class TheTakeIsOfTheThingNamedInItsClause(unittest.TestCase):
    """T53: "I pocket the coins and ask Rafe to strike the three gold from Mabel's ledger" let GRANT "ledger" in."""

    LINE = "I pocket the coins and ask Rafe to strike the three gold from Mabel's ledger as part of the day's pay."
    PROSE = ("You pocket the coins and call out to Rafe. He pulls a small knife from his belt and slices through the three "
             "gold marks. The paper shudders, the ink bleeding. The ledger is lighter, the debt lessened.")

    def test_the_ledger_is_not_taken(self):
        _pack()
        kept, rejected = _filter([{"name": "ledger", "quantity_delta": 1}], self.PROSE, self.LINE)
        self.assertEqual(kept, [], rejected)

    def test_a_second_thing_in_the_take_clause_is_taken(self):
        from app.world import _take_clause_names_item

        self.assertTrue(_take_clause_names_item("I pick up the key and the coin from the floor.", "coin", ["coin"]))
        self.assertFalse(_take_clause_names_item(self.LINE, "ledger", ["ledger"]))


class AKeyInALockIsNoPicking(unittest.TestCase):
    """T87: "I try the rusted key in the box's lock and open the lid" rolled lockpicking."""

    def test_no_lockpicking_with_a_key(self):
        from app.skill_checks import infer_check_from_action

        for line in ("I try the rusted key in the box's lock and open the lid.", "I unlock the chest with the brass key."):
            check = infer_check_from_action(line)
            self.assertFalse(check and check.get("skill_code") == "lockpicking", (line, check))


class AStrikeOnALedgerIsNoBlow(unittest.TestCase):
    """T53: "ask Rafe to strike the three gold from Mabel's ledger" rolled melee."""

    def test_no_melee(self):
        from app.skill_checks import infer_check_from_action

        check = infer_check_from_action("I pocket the coins and ask Rafe to strike the three gold from Mabel's ledger.")
        self.assertFalse(check and check.get("skill_code") == "melee", check)


class ASingleGoldPieceIsOne(unittest.TestCase):
    """T52: "three silver, two copper, and a single gold piece" dropped into the palm, and GOLD moderate rolled 31."""

    def test_coin_mentions_reads_one(self):
        from app.prose_state import coin_mentions

        self.assertEqual(coin_mentions("He dropped a handful of coins into your palm: three silver, two copper, and a single gold piece."), [1])
        self.assertEqual(coin_mentions("She counts out one gold coin."), [1])


class AWordInAnotherScriptGoes(unittest.TestCase):
    """T79-T80: "You're not the только person who's asked that" leaked and was echoed the next turn."""

    def test_the_token_is_dropped_and_the_sentence_kept(self):
        from app.prose_state import repair_meta_leaks

        text = "“You’re not the только person who’s asked that,” she says, her voice low."
        out, fixes = repair_meta_leaks(text)
        self.assertEqual(out, "“You’re not the person who’s asked that,” she says, her voice low.")
        self.assertIn("foreign_script", [f["why"] for f in fixes])

    def test_plain_prose_is_untouched(self):
        from app.prose_state import repair_meta_leaks

        text = "Nell’s brow furrows. “The reeve’s man had it,” she says."
        self.assertEqual(repair_meta_leaks(text)[0], text)


class ADroppedSentenceTakesItsQuoteAlong(unittest.TestCase):
    """T87: the sentence opening a quote was cut and 'Find it before the tide comes in.”' stayed as an orphan."""

    def test_the_rest_of_the_quote_goes_too(self):
        from app.prose_state import drop_sentences

        text = ("A name catches your eye. You unfold it, revealing a single line: “The reeve’s ledger is missing. "
                "Find it before the tide comes in.” The weight of the note feels heavier than the box itself, and you turn back.")
        out, dropped = drop_sentences(text, lambda s: "unfold" in s, floor=10)
        self.assertEqual(out, "A name catches your eye. The weight of the note feels heavier than the box itself, and you turn back.")
        self.assertEqual(len(dropped), 2)


class AVerifierPatchMayNotShrinkTheScene(unittest.TestCase):
    """T85: a "revise" replaced a 709-character scene with a 70-character summary and the fragment shipped."""

    DRAFT = ("The Hold is a place of quiet industry, its wooden beams groaning under the weight of salvaged crates. You move past "
             "the worker and head toward the far corner, where the tallest stacks loom. Behind the tallest stack, you spot a "
             "narrow passage, half-concealed by a tarp. You push through the dust, and in the dim light you spot a key dangling "
             "from a broken chain, half-buried in rust.")

    def test_the_draft_prose_stays(self):
        from app.llm import _merge_verifier_verdict

        merged = _merge_verifier_verdict(
            {"verdict": "revise", "issues": ["narration must be a single paragraph"],
             "patch": {"narration": "The hidden passage behind the tallest stacks, containing a rusted key."}},
            {"narration": self.DRAFT}, None,
        )
        self.assertEqual(merged.get("narration"), self.DRAFT)

    def test_a_real_rewrite_is_taken(self):
        from app.llm import _merge_verifier_verdict

        rewrite = self.DRAFT.replace("a key dangling", "a rusted key dangling")
        merged = _merge_verifier_verdict({"verdict": "revise", "patch": {"narration": rewrite}}, {"narration": self.DRAFT}, None)
        self.assertEqual(merged.get("narration"), rewrite)


class AnAnswerOpeningOnTheQuoteIsThePlayers(unittest.TestCase):
    """T91: after Nell's question, a paragraph opening on a bare "I found a few things ..." stood as the scene's."""

    LINE = ("I go inside and set the rusted box on Nell's desk. \"The guild's missing goods, from a hidden passage under the "
            "Hold. Thirty gold, as agreed.\"")
    PROSE = ("You go inside and set the rusted crate on Nell's desk. \"The guild's missing goods, from a hidden passage under "
             "the Hold. Thirty gold, as agreed,\" you say. The guildmaster's eyes narrow as she opens the crate.\n\n"
             "Nell's gaze flicks to you. \"You've brought it back,\" she says. \"But I need to know—did you find anything "
             "else? The passage was sealed tight.\"\n\n"
             "\"I found a few things. A map, some old tools, and... a name carved into the wall.\" You pause, the weight of the "
             "words settling on your tongue. \"It wasn't the guild's name. It was something else.\"\n\n"
             "Nell's brow furrows. \"A name?\" she repeats. \"Some things are better left buried.\"")

    def test_the_invented_answer_is_dropped_and_the_scene_cut(self):
        import re

        from app.llm import _scene_cut_point
        from app.narration_pipeline import drop_invented_player_speech

        _kept, spoken = drop_invented_player_speech(re.split(r"\n\s*\n", self.PROSE), self.LINE)
        self.assertTrue(any("I found a few things" in s for s in spoken), spoken)
        point = _scene_cut_point(self.PROSE, self.LINE)
        self.assertIsNotNone(point)
        self.assertIn("sealed tight", point["npc_line"])

    def test_the_other_persons_bare_line_with_a_player_beat_stays(self):
        import re

        from app.narration_pipeline import drop_invented_player_speech

        prose = ("You set the crate down. Nell looks up.\n\n\"Three gold?\" You hold her stare.\n\n"
                 "\"You've brought it back,\" she says.")
        _kept, spoken = drop_invented_player_speech(re.split(r"\n\s*\n", prose), "I set the crate down and wait.")
        self.assertEqual(spoken, [])


class AToldReportIsNotRetoldAsAStory(unittest.TestCase):
    """8B run 153, T6: "tell Eda I found the cargo ..." became an invented reply with a theft and a suspect."""

    LINE = ("I walk back to the dock and tell Eda I found the Black Tide's cargo at the old shipyard: three barrels, two "
            "crates and a bundle of salted fish and rum.")

    def test_a_voicing_with_words_of_its_own_goes_and_a_faithful_one_stays(self):
        import re

        from app.narration_pipeline import drop_invented_player_speech

        prose = ("You walk back to The Dock, where Eda waits.\n\n“You found it?” she asks, her tone edged with suspicion.\n\n"
                 "“Yes. The barrels and the crate are still sealed, but the fish and rum were already taken. I don’t know "
                 "who took them, but I think it’s someone who knew about the shipment.”")
        _kept, spoken = drop_invented_player_speech(re.split(r"\n\s*\n", prose), self.LINE)
        self.assertTrue(any("already taken" in s for s in spoken), spoken)
        faithful = ("You walk back to The Dock, where Eda waits.\n\n“You found it?” she asks.\n\n"
                    "“At the old shipyard. Three barrels, two crates and a bundle of salted fish and rum.” you tell her.")
        _kept, spoken = drop_invented_player_speech(re.split(r"\n\s*\n", faithful), self.LINE)
        self.assertEqual(spoken, [])


class ARepeatedPieceTakesItsTagAlong(unittest.TestCase):
    """T98: the repeated piece went and 'you repeat, the weight of the unspoken debt ...' stayed."""

    LINE = "\"Reeve. Mabel's three gold is struck. I'd hear from you what I'm owed.\" I wait."
    DRAFT = ("“Reeve. Mabel's three gold is struck. I'd hear from you what I'm owed,” you say. Raven's gaze lingers. "
             "“You mention Mabel's three gold,” he says.\n\n"
             "You cut him off with a raised hand. “I'd hear from you what I'm owed,” you repeat, the weight of the "
             "unspoken debt pressing against your ribs. Raven's jaw tightens.")

    def test_no_dangling_tag(self):
        from app.narration_pipeline import keep_player_words

        out, changes = keep_player_words(self.DRAFT, self.LINE)
        self.assertNotIn("you repeat", out)
        self.assertIn("Raven's jaw tightens.", out)
        self.assertIn("repeated_piece_of_line_dropped", [c.get("action") for c in changes])


class PraiseOfWorkIsNoJob(unittest.TestCase):
    def test_good_work_is_vetoed(self):
        from app import quest_offers as qo

        line = "You're doing good work, Flat-runner. The guild needs more hands, and you're helping out."
        self.assertEqual(qo._code_veto(line, asked_for_work=False), "praise_of_work")

    def test_an_offer_with_pay_stands(self):
        from app import quest_offers as qo

        line = "Good work. I've got another job for you: haul the nets in from the flats, two gold for the day."
        self.assertEqual(qo._code_veto(line, asked_for_work=False), "")


if __name__ == "__main__":
    unittest.main()
