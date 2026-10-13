"""7B run 27 (Qwen2.5 7B on MLE, agent as player): untagged repeats, a bar in the room, the cool evening."""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run27-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}

AVICE_T6 = ("Trouble? Oh, you'll see enough of it. The mudflats are treacherous, full of hidden dangers. Sometimes, we "
            "come across smugglers, or worse, the pirates who prowl the waters.")


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class UntaggedRepeatCreditedToTheWrongPerson(unittest.TestCase):
    """T7 (a Wait): Avice's T6 line came back untagged, was credited to the last name in the prose, and stayed."""

    def test_dropped(self):
        from app.narration_pipeline import drop_speech_said_before

        repeat = ('"Trouble? Oh, you\'ll see enough of it. The mudflats are treacherous, full of hidden dangers. '
                  'Sometimes, we come across strange lights or strange noises."')
        paras = ["Blessed Hound [[B]] watches over you from the shadows. Larkin's voice breaks the silence.", repeat]
        _kept, dropped = drop_speech_said_before(
            paras, [AVICE_T6], [f'"{AVICE_T6}"'], "__wait_request__: kind=wait", ["A"], {repeat: "B"}
        )
        self.assertEqual(dropped, [repeat])

    def test_a_tagged_line_keeps_its_own_speaker(self):
        from app.narration_pipeline import drop_speech_said_before

        tagged = '"Trouble? Oh, you\'ll see enough of it. The mudflats are treacherous, full of hidden dangers," Tam says.'
        _kept, dropped = drop_speech_said_before(
            [tagged], [AVICE_T6], [f'"{AVICE_T6}"'], "__wait_request__: kind=wait", ["A"], {tagged: "C"}
        )
        self.assertEqual(dropped, [])


class ABarInTheRoomIsNotABar(unittest.TestCase):
    """T5: "ask whoever is behind the bar" inside the Hound opened a closed "Saltmarrow Bar"."""

    def test_no_bar_minted(self):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            here = conn.execute("SELECT current_location_id FROM player").fetchone()[0]
            made = world._mint_venue_from_request(
                conn, here, "I go into the Twice-Blessed Hound and ask whoever is behind the bar for Captain Darrow.", ""
            )
        self.assertEqual(made, "")


class TheCoolEvening(unittest.TestCase):
    """T7: "a comforting presence in the cool evening" at 13:31."""

    def test_repaired(self):
        from app.prose_state import repair_clock_words

        text, fixes = repair_clock_words("A comforting presence in the cool evening.", 13)
        self.assertEqual(text, "A comforting presence in the cool afternoon.")
        self.assertEqual(fixes[0]["from"], "in the cool evening")
        self.assertEqual(repair_clock_words("They walk into the warm night.", 22)[1], [])


if __name__ == "__main__":
    unittest.main()
