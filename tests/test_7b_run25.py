"""7B run 25 (Qwen2.5 7B on MLE, agent as player): goods a seller hands over to look at are not bought."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run25-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}

LINE = ("I go over to the chandler's stall and look over what she has for sale - rope, lamp oil, anything "
        "I could use on the flats.")
PROSE = (
    "You approach Katerine's stall, the chandler's, and survey the goods with interest. A variety of ropes hang "
    "from hooks, and lamp oil jars sit neatly in a row.\n\n"
    'Katerine nods, her expression turning to one of professional pride. "Of course, I can offer you both. Here, '
    'this rope is well-made and strong. It\'s been tested in the worst of weather." She hands you a bundle of rope. '
    '"And this oil, it burns steadily without flickering. Just what you need for your work."'
)


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _filter(line, prose):
    from app import world
    from app.db import connect, init_db

    init_db()
    rejected: list = []
    with connect() as conn:
        conn.execute("DELETE FROM inventory")
        kept = world._filter_inventory_changes(
            conn, [{"name": "rope", "quantity_delta": 1}], narration=prose, player_input=line,
            draft_narration=prose, rejected=rejected,
        )
    return [c["name"] for c in kept if int(c.get("quantity_delta") or 0) > 0], rejected


class ShownForSaleIsNotBought(unittest.TestCase):
    """T1: the chandler handed over a bundle of rope to look at and it went into the pack, unpaid."""

    def test_not_granted_and_not_trimmed(self):
        kept, rejected = _filter(LINE, PROSE)
        self.assertEqual(kept, [])
        # Not refused as a gain to trim: she is holding the rope, and the prose stays.
        self.assertEqual(rejected, [])

    def test_a_gift_still_passes(self):
        prose = PROSE.replace("She hands you a bundle of rope.", "She hands you a bundle of rope. \"Take it, it's yours.\"")
        self.assertEqual(_filter(LINE, prose)[0], ["rope"])

    def test_a_purchase_still_passes(self):
        prose = PROSE.replace("She hands you a bundle of rope.", "You pay her two gold and she hands you a bundle of rope.")
        self.assertEqual(_filter(LINE, prose)[0], ["rope"])

    def test_coins_set_down_count_as_paid(self):
        # Run 5 T24: "you ask the keeper what a cot costs ... and put the four gold coins on the counter".
        prose = PROSE.replace("She hands you a bundle of rope.",
                              "You ask what it costs and put the coins on the counter. She hands you a bundle of rope.")
        self.assertEqual(_filter(LINE, prose)[0], ["rope"])

    def test_asking_to_buy_still_passes(self):
        self.assertEqual(_filter("I'll buy the rope from the chandler's stall.", PROSE)[0], ["rope"])

    def test_a_hand_over_outside_a_sale_still_passes(self):
        prose = 'Oldfield nods at the pile. "Well done." He hands you a coil of rope for your trouble.'
        self.assertEqual(_filter("I finish sorting the pile and tell Oldfield it's done.", prose)[0], ["rope"])


if __name__ == "__main__":
    unittest.main()
