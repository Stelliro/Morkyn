"""The engine ledger: every write, swallowed exception and second of a turn is on record."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-ledger-"))
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


def _fresh_save():
    from app.db import connect, init_db

    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM inventory")
        if not conn.execute("SELECT 1 FROM player WHERE id = 1").fetchone():
            conn.execute("INSERT INTO player (id, name) VALUES (1, 'Isk')")
        conn.execute("UPDATE player SET gold = 10 WHERE id = 1")


# Compiled under an app/ path so the exception monitor counts it as engine code.
_SWALLOWER_SRC = """
def swallow():
    try:
        int("not a number")
    except Exception:
        pass
"""


def _swallower():
    ns: dict = {}
    exec(compile(_SWALLOWER_SRC, str(ROOT / "app" / "_ledger_probe.py"), "exec"), ns)
    return ns["swallow"]


class LedgerRecordsTheTurn(unittest.TestCase):
    def setUp(self):
        _fresh_save()
        from app import turn_ledger

        turn_ledger.clear_last()
        path = turn_ledger.timings_path()
        if path.exists():
            path.unlink()

    def test_writes_delta_and_attribution(self):
        from app import turn_ledger
        from app.db import connect

        @turn_ledger.recorded("turn")
        def a_turn():
            with connect() as conn:
                conn.execute("UPDATE player SET gold = gold + 50 WHERE id = 1")
                conn.execute("INSERT INTO inventory (name, quantity) VALUES ('brass fitting', 2)")
            turn_ledger.note("gold", "settled", detail={"gold_delta": 50})

        a_turn()
        body = turn_ledger.last_finished()
        self.assertTrue(body["complete"])
        gold = body["delta"]["player"]["gold"]
        self.assertEqual((gold["from"], gold["to"]), (10, 60))
        write = body["writes"][gold["writes"][0]]
        self.assertEqual((write["op"], write["table"]), ("UPDATE", "player"))
        self.assertEqual(body["delta"]["inventory"]["brass fitting"], {"from": 0, "to": 2})
        self.assertEqual(body["notes"][0]["decision"], "settled")
        # The code that wrote is named (this test is outside app/, so the frames
        # list is empty here; inside the engine it holds file:line function).
        self.assertIn("at", write)

    def test_nested_entry_points_share_one_ledger(self):
        from app import turn_ledger
        from app.db import connect

        @turn_ledger.recorded("turn")
        def inner():
            with connect() as conn:
                conn.execute("UPDATE player SET gold = gold - 3 WHERE id = 1")

        @turn_ledger.recorded("wait")
        def outer():
            with connect() as conn:
                conn.execute("UPDATE player SET energy = 5 WHERE id = 1")
            inner()

        outer()
        body = turn_ledger.last_finished()
        self.assertEqual(body["label"], "wait")
        self.assertEqual(len([w for w in body["writes"] if w["table"] == "player"]), 2)

    def test_swallowed_exceptions_are_listed(self):
        from app import turn_ledger

        swallow = _swallower()

        @turn_ledger.recorded("turn")
        def a_turn():
            swallow()
            swallow()

        a_turn()
        body = turn_ledger.last_finished()
        hits = [s for s in body["swallowed"] if s["caught_in"].startswith("_ledger_probe.py")]
        self.assertEqual(len(hits), 1, body["swallowed"])
        self.assertEqual((hits[0]["type"], hits[0]["count"]), ("ValueError", 2))
        # Outside a turn nothing is monitored.
        swallow()

    def test_converter_fallbacks_are_routine_and_listed_last(self):
        from app import turn_ledger

        ns: dict = {}
        src = "def _int(v):\n    try:\n        return int(v)\n    except Exception:\n        return 0\n"
        exec(compile(src, str(ROOT / "app" / "_ledger_probe2.py"), "exec"), ns)
        swallow = _swallower()

        @turn_ledger.recorded("turn")
        def a_turn():
            ns["_int"](None)
            swallow()

        a_turn()
        mine = [s for s in turn_ledger.last_finished()["swallowed"] if s["caught_in"].startswith("_ledger_probe")]
        self.assertEqual([bool(s.get("routine")) for s in mine], [False, True])

    def test_timings_line_with_gap_and_model_time(self):
        from app import turn_ledger

        @turn_ledger.recorded("turn")
        def a_turn():
            with turn_ledger.phase("draft"):
                turn_ledger.model_call(1.5, 0.25, 1000, 200)

        a_turn()
        time.sleep(0.05)
        a_turn()
        lines = [json.loads(l) for l in turn_ledger.timings_path().read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertIsNone(lines[0]["gap_since_previous"])
        self.assertGreaterEqual(lines[1]["gap_since_previous"], 0.04)
        self.assertEqual((lines[1]["model_seconds"], lines[1]["gpu_wait_seconds"]), (1.5, 0.25))
        self.assertEqual(lines[1]["model_call_count"], 1)
        self.assertEqual(lines[1]["phases"][0]["phase"], "draft")

    def test_requests_line(self):
        from app import turn_ledger
        from app.world import model_trace_dir

        now = time.time()
        turn_ledger.log_request("POST", "/api/randomize-setup", 200, now - 2.0, now)
        last = (model_trace_dir() / "requests.jsonl").read_text(encoding="utf-8").splitlines()[-1]
        line = json.loads(last)
        self.assertEqual((line["path"], line["status"], line["seconds"]), ("/api/randomize-setup", 200, 2.0))

    def test_no_ledger_no_cost(self):
        from app import turn_ledger
        from app.db import connect

        with connect() as conn:
            conn.execute("UPDATE player SET gold = 1 WHERE id = 1")
        self.assertIsNone(turn_ledger.current())
        turn_ledger.note("gold", "ignored")
        turn_ledger.model_call(1.0, 0.0, 1, 1)


if __name__ == "__main__":
    unittest.main()
