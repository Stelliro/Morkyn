"""
A sentence said once in a turn must not be said again later in that turn.

The case these tests are built from is a real playtest turn. The model opened a
caravanserai scene, then wrote two more paragraphs that re-used whole sentences
from the ones above them, word for word:

    P2  "...A potboy sweeps past, his broom kicking up dust..."
    P3  "A potboy sweeps past, his broom kicking up dust..."      <- verbatim
    P4  "The clatter of a merchant's scales echoes..."            <- verbatim from P2

The existing pair walker did not catch any of it. It only ever compares a
paragraph to the one directly above it, and it scores whole paragraphs with
token Jaccard: P3 and P4 share a forty-word clause verbatim and still measure
45%, under the 48% reject bar, because each paragraph also carries a different
sentence that dilutes the score. P2 and P4 are two apart and were never
compared at all.
"""

import unittest

from app.narration_pipeline import (
    NarrationLedger,
    cascade_fix_pairs,
    consolidate_scene_heuristic,
    drop_repeated_sentences,
    split_sentences,
)

P1 = (
    "You step into the Silk Road Caravanserai, the scent of spiced tea and drying wool "
    "thick in the air, and find Darien already waiting by the hearth, his hands wrapped "
    "around a clay mug, while Lirael leans against the counter, idly twisting the silver "
    "ring on her finger. Your water bottle is empty, and your satchel feels lighter than "
    "when you left the last town, though your inventory shows nothing missing."
)
POTBOY = (
    "A potboy sweeps past, his broom kicking up dust that swirls in the dim light, and you "
    "catch the faint tang of burnt incense lingering near the prayer corner."
)
SCALES = (
    "The clatter of a merchant’s scales echoes from the far end of the hall as a group "
    "of traders haggle over bolts of indigo fabric, their voices rising above the low hum "
    "of conversation."
)
HEARTH = (
    "Darien is already waiting by the hearth, his hands wrapped around a clay mug, while "
    "Lirael leans against the counter, idly twisting thread into a spool, her gaze flicking "
    "toward you with the quiet weight of someone who knows the price of silence."
)

REAL_TURN = [P1, f"{SCALES} {POTBOY}", f"{POTBOY} {HEARTH}", f"{SCALES} {HEARTH}"]


class SplitSentencesTests(unittest.TestCase):
    def test_splits_on_terminators(self):
        self.assertEqual(
            split_sentences("One thing happened. Then another! And a third?"),
            ["One thing happened.", "Then another!", "And a third?"],
        )

    def test_empty_text_is_no_sentences(self):
        self.assertEqual(split_sentences(""), [])
        self.assertEqual(split_sentences("   "), [])


class DropRepeatedSentencesTests(unittest.TestCase):
    def test_the_real_turn_loses_every_repeat_and_keeps_every_original(self):
        kept, dropped = drop_repeated_sentences(REAL_TURN)
        body = " ".join(kept)

        # Four reused sentences: the potboy and the scales lifted verbatim, and
        # the hearth clause twice -- it never matches a whole sentence, because
        # P1 wraps it inside a longer opening, so it is the shared-run rule that
        # catches it rather than the verbatim or near-match one.
        self.assertEqual(len(dropped), 4)
        for once in (POTBOY, SCALES):
            self.assertEqual(body.count(once), 1, f"expected exactly one copy of: {once[:40]}")

        # The opening paragraph is untouched. The last two were built entirely
        # out of repeats, so they empty rather than survive as stubs.
        self.assertEqual(kept[0], P1)
        self.assertEqual(kept[2], "")
        self.assertEqual(kept[3], "")

    def test_a_reused_clause_inside_a_longer_sentence_is_caught(self):
        """
        The one the paragraph-overlap score cannot see. P1 buries the hearth
        clause in a longer opening sentence, so no sentence matches any other
        sentence -- but twenty consecutive words are shared.
        """
        kept, dropped = drop_repeated_sentences([P1, HEARTH])
        self.assertEqual(len(dropped), 1)
        self.assertEqual(kept[0], P1, "the first use is always the one that survives")
        self.assertEqual(kept[1], "")

    def test_an_ordinary_shared_phrase_is_not_a_repeat(self):
        """A few words in common must not cost a sentence; only long runs do."""
        kept, dropped = drop_repeated_sentences(
            [
                "He leans against the counter and studies the ledger without speaking.",
                "She leans against the counter and counts the coins into a small stack.",
            ]
        )
        self.assertEqual(dropped, [])
        self.assertEqual(len(list(filter(None, kept))), 2)

    def test_output_stays_aligned_with_input(self):
        kept, _ = drop_repeated_sentences(REAL_TURN)
        self.assertEqual(len(kept), len(REAL_TURN))

    def test_a_sentence_said_once_is_never_dropped(self):
        paragraphs = ["First and quite distinct. Second and also distinct.", "A third, wholly unrelated."]
        kept, dropped = drop_repeated_sentences(paragraphs)
        self.assertEqual(dropped, [])
        self.assertEqual(kept, paragraphs)

    def test_distance_does_not_matter(self):
        """P2 and P4 are two apart -- the pair walker never compared them."""
        kept, dropped = drop_repeated_sentences([SCALES, "Filler between.", "More filler here.", SCALES])
        self.assertEqual(len(dropped), 1)
        self.assertEqual(kept[3], "")

    def test_short_lines_may_repeat(self):
        """Dialogue and beats legitimately echo; only substantial sentences are policed."""
        kept, dropped = drop_repeated_sentences(['"I know," he said.', 'She waited.', '"I know," he said.'])
        self.assertEqual(dropped, [])
        self.assertEqual(len(list(filter(None, kept))), 3)

    def test_near_duplicates_count_as_repeats(self):
        near = SCALES.replace("indigo fabric", "indigo cloth")
        kept, dropped = drop_repeated_sentences([SCALES, near])
        self.assertEqual(len(dropped), 1)
        self.assertEqual(kept[1], "")

    def test_paragraph_breaks_inside_one_block_survive(self):
        block = f"{P1}\n\n{SCALES}"
        kept, dropped = drop_repeated_sentences([block, POTBOY])
        self.assertEqual(dropped, [])
        self.assertIn("\n\n", kept[0])

    def test_never_empties_the_whole_turn(self):
        kept, _ = drop_repeated_sentences([SCALES, SCALES])
        self.assertTrue(any(k.strip() for k in kept), "a turn must never be reduced to nothing")

    def test_handles_empty_input(self):
        self.assertEqual(drop_repeated_sentences([]), ([], []))


SHED_AIR_FIRST = (
    "You stand before a rusted shed at the edge of a quiet village, its lock stiff with age "
    "and neglect, the air inside thick with the scent of oil and metal."
)
SHED_AIR_AGAIN = (
    "The air inside the shed is thick with the scent of oil and metal, the silence broken "
    "only by the faint creak of shifting tools."
)
SHED_CHAIN_FIRST = (
    "A faint glint catches your eye near the back — a rusted chain, still attached to a "
    "wooden crate, its surface marked with initials you don't recognize."
)
SHED_CHAIN_AGAIN = (
    "A rusted chain, still attached to a wooden crate, glints in the dim light, its surface "
    "etched with initials you don't recognize."
)


class ParaphrasedRepeatTests(unittest.TestCase):
    """
    A second reported turn, and the one that set the shared-run threshold.

    Nothing here is reused verbatim: the model re-skins the sentence around the
    clause it is repeating. Whole-sentence and near-match rules both miss it --
    these pairs measure 0.34 and 0.54 token overlap against a 0.85 bar -- and
    the shared runs are only 8 and 9 words, so a threshold of twelve caught
    neither.
    """

    def test_a_reskinned_scent_line_is_a_repeat(self):
        kept, dropped = drop_repeated_sentences([SHED_AIR_FIRST, SHED_AIR_AGAIN])
        self.assertEqual(len(dropped), 1)
        self.assertEqual(kept[0], SHED_AIR_FIRST, "the first telling survives")

    def test_a_reskinned_chain_line_is_a_repeat(self):
        kept, dropped = drop_repeated_sentences([SHED_CHAIN_FIRST, SHED_CHAIN_AGAIN])
        self.assertEqual(len(dropped), 1)

    def test_the_new_detail_in_that_paragraph_is_kept(self):
        """Dropping the echo must not cost the sentence that carried news."""
        crate = "The crate itself is sealed, but the tools around it wait for someone to pick up where the last user left off."
        kept, _ = drop_repeated_sentences([SHED_CHAIN_FIRST, f"{SHED_CHAIN_AGAIN} {crate}"])
        self.assertIn("The crate itself is sealed", kept[1])
        self.assertNotIn("glints in the dim light", kept[1])


class ConsolidatorReachTests(unittest.TestCase):
    def test_consolidator_compares_against_every_earlier_paragraph(self):
        """A paragraph duplicating paragraph 1 is as bad as one duplicating paragraph 3."""
        ledger = NarrationLedger(turn=1, player_input="look", budget={})
        paragraphs = [SCALES, "Something entirely different happens here instead.", SCALES]
        cleaned = consolidate_scene_heuristic(paragraphs, ledger)
        self.assertEqual(len(cleaned), 2, "the far-back duplicate should be dropped")


class RegressionGuardTests(unittest.TestCase):
    def test_pair_walker_alone_still_misses_it(self):
        """
        Pinned so nobody 'simplifies' the sentence pass away later: the adjacent
        pair walker on its own returns this turn completely unchanged.
        """
        kept, _ = cascade_fix_pairs(list(REAL_TURN))
        self.assertEqual(len(kept), 4)


if __name__ == "__main__":
    unittest.main()
