"""Review of the playtest #16 (a) venue fixes (game 2, "Eldoria's Edge").

- The entry reader took spoken invitations ("Why don't you step into my
  shop?") and "in front of" / "in the direction of" as the player going
  inside, which mints a venue and moves the player into it.
- The shown-entry rule ran before the travel rules, so an inn entered at the
  end of a journey was opened inside the place the player had left.
- The venue rule still shipped two sample building names.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-review-places-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import db, venues, world  # noqa: E402
from app.db import connect  # noqa: E402

class EntryNeedsTheNarrationToGoInside(unittest.TestCase):
    def test_not_an_entry(self):
        for text in (
            'Elara smiles. "Why don\'t you step into my shop?" she asks.',
            "You step in front of the bakery and wait.",
            "You head in the direction of the inn.",
            "She lets you in on a secret about the tavern.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(venues.entry_in_prose(text, ["Elara", "Aria"]))

    def test_turn3_entry_still_reads(self):
        text = (
            '"Can I help you?" she asks, her voice tinged with suspicion. Aria [[A]] introduces herself and '
            "explains that you saw a hooded figure enter the shop. Elara nods and gestures for you to come in. "
            "Inside, the shop is cluttered with various goods, and the air is thick with the scent of herbs."
        )
        shown = venues.entry_in_prose(text, ["Aria", "Elara"])
        self.assertIsNotNone(shown)
        self.assertEqual(shown["keeper"], "Elara")
        self.assertEqual(shown["noun"], "shop")


def seed_edge() -> None:
    db.init_db()
    with connect() as conn:
        conn.execute("UPDATE player SET current_location_id = 1 WHERE id = 1")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM locations WHERE id != 1")
        conn.execute(
            "UPDATE locations SET name = 'Eldoria''s Edge', parent_id = 0, kind = '', settlement_size = 'town', "
            "keeper_npc_id = 0 WHERE id = 1"
        )
        conn.execute(
            "INSERT INTO locations (code, name, summary, visit_count) VALUES ('L2', 'Millbrook', 'A river town.', 0)"
        )


class EntryAfterAJourneyIsNotHere(unittest.TestCase):
    """The shown-entry rule ran before the travel rules, so an inn reached at the end of a journey
    was opened inside the place the player had just left."""

    def setUp(self):
        seed_edge()

    def resolve(self, player_input, prose, **extra):
        result = {"narration": prose, "player": {}, **extra}
        with connect() as conn:
            report = world.resolve_movement(conn, result, player_input, intent="travel", narration=prose)
            venues_here = conn.execute("SELECT COUNT(*) FROM locations WHERE parent_id = 1").fetchone()[0]
        return report, venues_here

    def test_new_place_then_an_inn(self):
        report, venues_here = self.resolve(
            "I set off along the river road",
            "You reach Riverford at dusk. You step into the inn by the bridge.",
            locations=[{"name": "Riverford", "summary": "A ford town."}],
        )
        self.assertEqual(report.get("rule"), "new_location")
        self.assertEqual(report.get("destination"), "Riverford")
        self.assertEqual(venues_here, 0)

    def test_known_place_named_then_a_tavern(self):
        report, venues_here = self.resolve(
            "I walk to Millbrook", "You arrive in Millbrook. You duck into the tavern out of the rain."
        )
        self.assertNotEqual(report.get("rule"), "venue_shown")
        self.assertEqual(venues_here, 0)

    def test_a_shop_entered_here_is_still_a_venue(self):
        report, venues_here = self.resolve(
            "I follow her", "Elara nods and gestures for you to come in. Inside, the shop is cluttered."
        )
        self.assertEqual(report.get("rule"), "venue_shown")
        self.assertEqual(venues_here, 1)


class VenueRuleNamesNoSample(unittest.TestCase):
    def test_venue_rule_has_no_sample_building(self):
        state = {
            "current_location": {"code": "L1", "name": "Eldoria's Edge", "settlement_size": "village"},
            "locations": [{"code": "L1", "name": "Eldoria's Edge"}],
        }
        rule = world.movement_contract(state, "go into the shop", "travel").get("venue_rule") or ""
        self.assertIn("Interiors are places", rule)
        self.assertNotIn("Salt Crow", rule)
        self.assertNotIn("Apothecary", rule)


if __name__ == "__main__":
    unittest.main()
