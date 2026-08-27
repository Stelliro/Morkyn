"""Does the action table still fire when the player writes in -ing?

`infer_check_from_action` IS the check mechanism: it reads the player's own
sentence and picks the skill to roll. Every pattern in SKILL_TRIGGER_PATTERNS
is written `\\b(word|word)\\b`, which means the trailing boundary rejects every
inflected form of every trigger. A player typing "I'm sneaking past him" got no
check at all -- measured 8/8 base forms matching and 0/8 inflected.

The same trailing `\\b` also silently killed the stems that were deliberately
written as prefixes: `impersonat`, `gambl`, `necro`, `exorc`, `alchem`,
`navigat`, `cartograph`. `impersonat\\b` cannot match "impersonating" -- there
is no word boundary between "t" and "i" -- so it only ever matched the literal
non-word "impersonat". They were dead the day they were written.

The TRAPS block is the other half and matters more. Deleting the trailing `\\b`
outright is the obvious fix and it is wrong: it turns "ready" into read,
"between" into bet, "lieutenant" into lie, "control" into con and "maple" into
map. Those six are pinned here so nobody reaches for the easy version.

Run:  python -m unittest tests.test_action_inference_corpus
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-actioncorpus-test-"))
os.environ.update({
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
})

from app.skill_checks import infer_check_from_action  # noqa: E402

# (action text, expected skill code). Ordering matters: the table is
# first-match-wins, so each phrase here avoids words claimed by an earlier row.
BASE_FORMS: list[tuple[str, str]] = [
    ("I attack the guard", "melee"),
    ("I shoot the drone", "ranged"),
    ("I sneak past the guard", "stealth"),
    ("I persuade the merchant", "persuasion"),
    ("I haggle over the pelt", "appraise"),
    ("I bluff my way in", "deception"),
    ("I intimidate the clerk", "intimidation"),
    ("I climb the wall", "athletics"),
    ("I unlock the chest", "lockpicking"),
    ("I bandage the wound", "healing"),
]

# The whole point. Same verbs, written the way people actually type.
INFLECTED_FORMS: list[tuple[str, str]] = [
    ("I'm attacking the guard", "melee"),
    ("shooting at the drone", "ranged"),
    ("I'm sneaking past the guard", "stealth"),
    ("she was persuading the merchant", "persuasion"),
    ("I haggled over the pelt", "appraise"),
    ("he kept bluffing", "deception"),
    ("I'm intimidating the clerk", "intimidation"),
    ("climbing the wall", "athletics"),
    ("unlocking the chest", "lockpicking"),
    ("bandaging the wound", "healing"),
    ("I'm hiding behind the crates", "stealth"),
    ("searching the drawers", "perception"),
    ("I tracked the deer for hours", "survival"),
    ("smithing a fresh blade", "smithing"),
    ("disguising myself", "disguise"),
]

# Stems written as prefixes whose trailing \b made them unmatchable.
DEAD_STEMS: list[tuple[str, str]] = [
    ("impersonating the captain", "disguise"),
    ("gambling with the sailors", "gambling"),
    ("exorcising the haunted doll", "exorcism"),
    ("the alchemist mixes a draught", "alchemy"),
    ("navigating the reef", "navigation"),
    ("cartography of the coast", "cartography"),
    ("necromancy is forbidden here", "necromancy"),
]

# Words that CONTAIN a trigger but are not it. Dropping the trailing \b to fix
# the inflection gap makes every one of these fire. They must all stay silent.
TRAPS: list[tuple[str, str]] = [
    ("I get ready for the journey", "read -> investigation"),
    ("the gap between the stones", "bet -> gambling"),
    ("the lieutenant salutes", "lie -> deception"),
    ("I check the control panel", "con -> deception"),
    ("a maple grows by the door", "map -> cartography"),
    ("a contract binds them", "con -> deception"),
    ("the readying of the fleet", "read -> investigation"),
]


def _code(text: str) -> str | None:
    out = infer_check_from_action(text)
    if not isinstance(out, dict):
        return None
    return str(out.get("skill_code") or out.get("code") or "") or None


class TestBaseFormsStillWork(unittest.TestCase):
    def test_base_forms(self):
        for text, expected in BASE_FORMS:
            with self.subTest(text=text):
                self.assertEqual(_code(text), expected)


class TestInflectedFormsResolve(unittest.TestCase):
    def test_inflected_forms(self):
        misses = [(t, e, _code(t)) for t, e in INFLECTED_FORMS if _code(t) != e]
        self.assertEqual(
            misses,
            [],
            f"{len(misses)}/{len(INFLECTED_FORMS)} inflected actions did not resolve",
        )


class TestDeadPrefixStemsResolve(unittest.TestCase):
    def test_dead_stems(self):
        misses = [(t, e, _code(t)) for t, e in DEAD_STEMS if _code(t) != e]
        self.assertEqual(
            misses,
            [],
            f"{len(misses)}/{len(DEAD_STEMS)} prefix stems still unmatchable",
        )


class TestNoSubstringFalsePositives(unittest.TestCase):
    """The reason the fix is not "delete the trailing \\b"."""

    def test_traps_stay_silent(self):
        fired = [(t, why, _code(t)) for t, why in TRAPS if _code(t) is not None]
        self.assertEqual(fired, [], f"{len(fired)} trap phrase(s) matched a skill")


class TestNonActionsStaySilent(unittest.TestCase):
    def test_empty_and_meta(self):
        self.assertIsNone(_code(""))
        self.assertIsNone(_code("__meta__"))
        self.assertIsNone(_code("I wait quietly"))


if __name__ == "__main__":
    unittest.main()
