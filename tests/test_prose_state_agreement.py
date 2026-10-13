"""The prose and the turn's state agree (8B #55, #76) and auto context never breaks a turn (#62).

#55  The state did not follow reasonable prose: a person's pronouns flipped
     from the sex the story had set ("Min ... his weathered face"), and an
     item the player asked to take and the prose showed taken was never
     granted when the draft wrote no GRANT.
#76  A MOVE into a shop from a place with no parent (old saves: the tally
     house) ended "outside" while the prose was inside the shop.
#62  Auto context followed free VRAM down to 4096 on a shared GPU, below what
     even the compact contract needs, so every turn broke silently.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-prose-agreement-"))
_ENV = isolated_data_env(str(_TMP))
os.environ.update(_ENV)

from app import db, llm, model_limits, prose_state, world  # noqa: E402
from app.db import connect  # noqa: E402

_SAVED_ENV: dict[str, str | None] = {}
GIB = 1024 ** 3


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def seed() -> None:
    """Saltmarrow (L1), the chandlery inside it (L2), the parentless tally house (L3, an old save)."""
    db.init_db()
    with connect() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM npcs")
        conn.execute("DELETE FROM inventory")
        conn.execute("DELETE FROM locations WHERE id != 1")
        conn.execute("DELETE FROM settings WHERE key IN ('active_scene', 'conversation', 'scene_thread')")
        conn.execute(
            "UPDATE locations SET code = 'L1', name = 'Saltmarrow', summary = 'A drowned town.', parent_id = 0, "
            "kind = '', settlement_size = 'town', keeper_npc_id = 0 WHERE id = 1"
        )
        conn.execute(
            "INSERT INTO locations (id, code, name, summary, visit_count, parent_id, kind, open_minute, close_minute) "
            "VALUES (2, 'L2', 'Philippa Kemp''s General Store', 'The chandlery.', 2, 1, 'general_store', 0, 1440)"
        )
        conn.execute(
            "INSERT INTO locations (id, code, name, summary, visit_count, parent_id, kind) "
            "VALUES (3, 'L3', 'The Tally House', 'Where the tide clerk keeps the board.', 1, 0, '')"
        )
        conn.execute(
            "INSERT INTO npcs (id, code, location_id, name, role, attitude, pronouns) "
            "VALUES (1, 'A', 2, 'Philippa Kemp', 'chandler', 'neutral', 'she')"
        )
        conn.execute(
            "INSERT INTO npcs (id, code, location_id, name, role, attitude, pronouns) "
            "VALUES (2, 'B', 3, 'Min Yardley', 'tide clerk', 'neutral', 'she')"
        )
        conn.execute(
            "INSERT INTO npcs (id, code, location_id, name, role, attitude, pronouns) "
            "VALUES (3, 'C', 3, 'Hereward Jessop', 'boatman', 'neutral', 'he')"
        )
        conn.execute("UPDATE player SET current_location_id = 3 WHERE id = 1")


def _here() -> int:
    with connect() as conn:
        return int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0])


class ShopEnteredFromAParentlessPlace(unittest.TestCase):
    """#76 reopened (Saltmarrow T7, T73, T88)."""

    def setUp(self):
        seed()

    def _move(self, line: str, prose: str) -> dict:
        result = {"player": {"move_to_location": "Philippa Kemp's General Store"}, "narration": prose}
        with connect() as conn:
            report = world.resolve_movement(conn, result, line, intent=world._turn_intent(line)[0], narration=prose)
            world._apply_player(conn, result["player"])
        return report

    def test_the_prose_goes_in_so_the_player_is_in(self):
        line = "I go along the wall to Philippa's chandlery."
        prose = (
            "You follow the wall past the tally board and duck in through the low door of Philippa Kemp's "
            "General Store. Inside, rope and lamp oil crowd the shelves, and Philippa looks up from her ledger."
        )
        self._move(line, prose)
        self.assertEqual(_here(), 2)

    def test_a_walk_that_stops_outside_still_stops_outside(self):
        line = "I go along the wall to Philippa's chandlery."
        prose = "You follow the wall toward the chandlery. Gulls sit on its roof, and the door is shut against the wind."
        self._move(line, prose)
        self.assertEqual(_here(), 1)


class PronounsKeepTheSexTheStorySet(unittest.TestCase):
    """#55: Min is a woman in T1/T2 and 'his weathered face' in T4."""

    CAST = [{"names": ["Min Yardley", "Min"], "key": "she"}, {"names": ["Hereward Jessop", "Hereward"], "key": "he"}]

    def fix(self, text: str) -> str:
        return prose_state.repair_pinned_pronouns(text, self.CAST)[0]

    def test_a_flip_in_the_naming_sentence_and_the_next(self):
        text = "Min sets down the ladle and rubs his hands. His weathered face creases into a smile."
        self.assertEqual(
            self.fix(text),
            "Min sets down the ladle and rubs her hands. Her weathered face creases into a smile.",
        )

    def test_object_and_possessive_her_become_him_and_his(self):
        text = "Hereward wipes her brow. You hand her the rope, and she coils it over her shoulder."
        self.assertEqual(
            self.fix(text),
            "Hereward wipes his brow. You hand him the rope, and he coils it over his shoulder.",
        )

    def test_someone_else_in_the_sentence_leaves_it_alone(self):
        for text in (
            "Min nods to the boy. He grins and runs off.",
            "Min glances at Hereward. He shrugs.",
            "Min and the old man share a look; his eyes are tired.",
        ):
            self.assertEqual(self.fix(text), text)

    def test_speech_is_never_touched(self):
        text = 'Min frowns. "He left at dawn, and his boat with him."'
        self.assertEqual(self.fix(text), text)

    def test_a_correct_sentence_is_unchanged(self):
        text = "Min pulls her shawl tighter. She says nothing."
        self.assertEqual(self.fix(text), text)

    def test_the_reconcile_step_reads_the_pins(self):
        seed()
        result = {"narration": "Min Yardley sets down the ladle. His weathered face creases into a smile."}
        with connect() as conn:
            report = world._reconcile_prose_with_state(
                conn, result, rejected=[], movement_report={}, gold_note=None, purse_note=None
            )
        self.assertIn("Her weathered face", result["narration"])
        self.assertTrue(any(entry.get("why") == "pronouns_kept" for entry in report["trimmed"]))


class TakesShownAndAskedAreKept(unittest.TestCase):
    """#55: 'You lift it ... a silver coin' with no coin granted (the draft wrote no GRANT)."""

    def setUp(self):
        seed()

    def grant(self, line: str, prose: str, changes=None, rejected=None) -> list[dict]:
        with connect() as conn:
            return world._grant_shown_takes(conn, list(changes or []), prose, line, rejected=list(rejected or []))

    def names(self, changes) -> list[str]:
        return [str(c.get("name")) for c in changes if int(c.get("quantity_delta") or 0) > 0]

    def test_a_take_the_player_asked_for_is_granted(self):
        line = "I take the rusty key and the faded map from the drawer and keep them."
        prose = "You take the rusty key and the faded map from the drawer and slip them into your coat."
        self.assertEqual(sorted(self.names(self.grant(line, prose))), ["faded map", "rusty key"])

    def test_whatever_is_under_it(self):
        line = "I lift the loose stone and take whatever is under it."
        prose = "You lift the loose stone. Beneath it lies a silver coin, green at the rim, and you pocket it."
        self.assertEqual(self.names(self.grant(line, prose)), ["silver coin"])

    def test_no_take_in_the_line_grants_nothing(self):
        line = "I look under the loose stone."
        prose = "You lift the stone. A silver coin lies beneath it, and you pocket it."
        self.assertEqual(self.grant(line, prose), [])

    def test_a_grant_already_written_is_not_doubled(self):
        line = "I take the rusty key."
        prose = "You take the rusty key."
        changes = [{"name": "rusty key", "quantity_delta": 1}]
        self.assertEqual(len(self.grant(line, prose, changes)), 1)

    def test_put_back_or_a_refused_gain_is_not_granted(self):
        line = "I take the rusty key."
        self.assertEqual(self.grant(line, "You take the rusty key, weigh it, and put it back on the shelf."), [])
        refused = [{"name": "rusty key", "tokens": ["rusty", "key"], "outcome": "gain"}]
        self.assertEqual(self.grant(line, "You take the rusty key.", rejected=refused), [])

    def test_perception_and_people_are_not_items(self):
        line = "I take a look around and take Hereward's hand."
        prose = "You take a look around. You take Hereward's hand and he pulls you up."
        self.assertEqual(self.grant(line, prose), [])


class AutoContextKeepsATurnRunning(unittest.TestCase):
    """#62: a game holding ~9.5 GB of a 12 GB card left room for 4096 tokens."""

    FACTS = {"kind": "gguf", "params_b": 8.0, "n_ctx_train": 40960, "kv_bytes_per_token": 147456, "file_bytes": int(4.7 * GIB)}
    SHARED = {"total_bytes": 12 * GIB, "free_bytes": int(2.3 * GIB)}

    def test_auto_never_opens_below_what_a_turn_needs(self):
        needed = llm.estimated_tokens(llm.COMPACT_SYSTEM_PROMPT) + llm.MIN_TURN_HEADROOM_TOKENS
        context, why = model_limits.auto_context_tokens(self.FACTS, self.SHARED)
        self.assertGreaterEqual(context, needed)
        self.assertIn("free", why)

    def test_the_short_memory_is_reported(self):
        auto = model_limits.auto_limits(self.FACTS, self.SHARED)
        short = auto.get("short_of_memory")
        self.assertIsInstance(short, dict)
        self.assertLess(short["fits"], short["opened"])

    def test_the_shipped_default_path_warns(self):
        # No env override: the shipped auto path, as a player launches it.
        env = {k: v for k, v in os.environ.items() if k not in {"AI_RPG_CONTEXT_TOKENS", "AI_RPG_LLAMA_CPP_CONTEXT"}}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(
            model_limits, "model_facts", return_value=dict(self.FACTS, key="qwen3-8b")
        ), mock.patch.object(model_limits, "gpu_memory", return_value=dict(self.SHARED)), mock.patch.object(
            model_limits, "stored_limits", return_value=None
        ), mock.patch.object(llm, "get_model_config", return_value={"provider": "mle"}), mock.patch(
            "app.mle.loaded_context", return_value=0
        ):
            resolved = model_limits.resolve_limits(with_facts=False)
            notice = llm.context_contract_notice()
        self.assertEqual(resolved["source"]["context_tokens"], "auto")
        self.assertGreater(resolved["context_tokens"], model_limits.MIN_CONTEXT_TOKENS)
        self.assertIsNotNone(notice)
        self.assertEqual(notice["code"], "context_low_memory")


if __name__ == "__main__":
    unittest.main()
