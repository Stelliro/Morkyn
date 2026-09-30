"""MLE is the local provider. It loads a GGUF in-process."""
from __future__ import annotations

import ast
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="morkyn-mle-test-"))
os.environ["AI_RPG_DB"] = str(_TMP / "world.db")
os.environ["AI_RPG_LAUNCHER_PREFS"] = str(_TMP / "launcher_prefs.json")
os.environ.pop("MLE_MODEL", None)
os.environ.pop("MLE_GGUF", None)

from app import llm
from app.llm import _normalize_provider, apply_theme_model_routing
from app.mle import MleNotReady, chat, piece_should_hide, resolve_model_path, status

_DRAFT_PHASES = {"draft", "draft_parse_retry", "draft_compact_retry", "draft_retry"}
_MUST_HIDE_FUNCS = {
    "_make_pipeline_paragraph_writer",
    "_retry_missing_narration",
    "_try_dsl_draft",
}
_BANNED_PHASES = {
    "verify",
    "verify_compact_retry",
    "narration_consolidate",
    "ambient_move",
    "input_suggestions",
}


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _phase_of(node: ast.Call) -> str | None:
    for kw in node.keywords:
        if kw.arg != "phase":
            continue
        value = kw.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
        if isinstance(value, ast.JoinedStr):
            parts: list[str] = []
            for part in value.values:
                if isinstance(part, ast.Constant):
                    parts.append(str(part.value))
                else:
                    parts.append("{expr}")
            return "".join(parts)
        if isinstance(value, ast.Name):
            return None
    return None


def _has_hide(node: ast.Call) -> bool:
    return any(kw.arg in {"hide_words", "keep_words"} for kw in node.keywords)


class TestMleProvider(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.models = Path(self._tmp.name) / "models"
        self.models.mkdir()
        self._env = patch.dict(os.environ, {"MLE_MODEL": "", "MLE_GGUF": ""})
        self._dir = patch("app.mle.models_dir", return_value=self.models)
        self._env.start()
        self._dir.start()

    def tearDown(self):
        self._dir.stop()
        self._env.stop()
        self._tmp.cleanup()

    def test_known_providers_stay(self):
        self.assertEqual(_normalize_provider("mle"), "mle")
        self.assertEqual(_normalize_provider("llama_cpp"), "llama_cpp")
        self.assertEqual(_normalize_provider("openai"), "openai")
        self.assertEqual(_normalize_provider("xai"), "openai")

    def test_blank_or_unknown_is_mle(self):
        self.assertEqual(_normalize_provider(""), "mle")
        self.assertEqual(_normalize_provider("local-engine"), "mle")

    def test_theme_routing_sets_mle_model(self):
        out = apply_theme_model_routing(
            {
                "provider": "mle",
                "mle_model": "qwen3:8b",
                "theme_adapter_map": {"isekai_rpg": "morkyn-isekai-dm"},
            },
            {"adapter_hint": "isekai_rpg"},
        )
        self.assertEqual(out["mle_model"], "morkyn-isekai-dm")

    def test_chat_is_not_ready(self):
        with self.assertRaises(MleNotReady):
            chat(
                "system",
                "user",
                model="qwen3:8b",
                hide_words=["hooded"],
                keep_words=["baker"],
            )

    def test_status_is_not_ok(self):
        report = status("qwen3:8b")
        self.assertFalse(report["ok"])
        self.assertEqual(report["engine"], "MLE")
        self.assertEqual(report["model"], "qwen3:8b")
        self.assertIn(str(self.models), str(report["detail"]))
        self.assertNotIn("welding", str(report["detail"]).lower())

    def test_piece_should_hide_covers_whole_words_only(self):
        self.assertTrue(piece_should_hide("hooded", ["hooded"]))
        self.assertTrue(piece_should_hide(" hooded", ["hooded"]))
        self.assertTrue(piece_should_hide("\u2581hooded", ["hooded"]))
        self.assertFalse(piece_should_hide("hoo", ["hooded"]))
        self.assertFalse(piece_should_hide("ded", ["hooded"]))
        self.assertFalse(piece_should_hide("L1", ["L1", "hooded"]))
        self.assertFalse(piece_should_hide(" baker", ["baker"], ["baker"]))
        self.assertFalse(piece_should_hide("the", ["the"]))
        self.assertFalse(piece_should_hide("hooded.", ["hooded"]))
        self.assertFalse(piece_should_hide("a", ["a"]))
        self.assertFalse(piece_should_hide("12", ["12"]))

    def test_resolve_order_does_not_load(self):
        self.assertIsNone(resolve_model_path("qwen3:8b"))
        partial = self.models / "later.gguf.partial"
        partial.write_bytes(b"GGUF")
        self.assertIsNone(resolve_model_path("qwen3:8b"))
        only = self.models / "qwen2.5-7b-instruct-q4_k_m.gguf"
        only.write_bytes(b"GGUF")
        self.assertEqual(resolve_model_path("qwen3:8b"), only)
        named = self.models / "morkyn-isekai-dm.gguf"
        named.write_bytes(b"GGUF")
        self.assertEqual(resolve_model_path("morkyn-isekai-dm"), named)
        self.assertIsNone(resolve_model_path("qwen3:8b"))
        explicit = Path(self._tmp.name) / "explicit.gguf"
        explicit.write_bytes(b"GGUF")
        self.assertEqual(resolve_model_path(str(explicit)), explicit)
        with patch.dict(os.environ, {"MLE_MODEL": str(explicit)}):
            self.assertEqual(resolve_model_path("qwen3:8b"), explicit)
        with patch.dict(os.environ, {"MLE_GGUF": str(only), "MLE_MODEL": ""}):
            self.assertEqual(resolve_model_path("qwen3:8b"), only)

    def test_sample_cover_uses_journal_not_the_packet(self):
        db_path = Path(self._tmp.name) / "journal.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE journal (id INTEGER PRIMARY KEY AUTOINCREMENT, turn INTEGER NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL)"
        )
        line = "The hooded baker passed the hooded door."
        for turn in range(4):
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (?, 'narration', ?)",
                (turn, line),
            )
        conn.commit()
        conn.close()
        context = {
            "npcs": [{"name": "Mara", "role": "baker"}],
            "last_narration": " ".join(["lantern"] * 12),
        }
        with patch.dict(os.environ, {"AI_RPG_DB": str(db_path)}):
            hide, keep = llm._narration_sample_cover(context)
        self.assertIn("hooded", hide)
        self.assertIn("passed", hide)
        self.assertNotIn("baker", hide)
        self.assertNotIn("lantern", hide)
        self.assertIn("baker", keep)
        self.assertIn("mara", keep)
        self.assertIn("narration", keep)

    def test_sample_cover_falls_back_to_last_narration(self):
        missing = Path(self._tmp.name) / "empty" / "world.db"
        context = {"last_narration": " ".join(["hooded"] * 6)}
        with patch.dict(os.environ, {"AI_RPG_DB": str(missing)}):
            hide, _keep = llm._narration_sample_cover(context)
        self.assertIn("hooded", hide)

    def test_json_repair_does_not_copy_hide_words(self):
        calls = []

        def fake(*_args, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return "not json"
            return '{"ok": true}'

        with patch.object(llm, "_chat_content", side_effect=fake):
            parsed = llm._chat_json(
                "system",
                "user",
                hide_words=["hooded"],
                keep_words=["baker"],
            )
        self.assertEqual(parsed, {"ok": True})
        self.assertEqual(calls[0]["hide_words"], ["hooded"])
        self.assertEqual(calls[0]["keep_words"], ["baker"])
        self.assertNotIn("hide_words", calls[1])
        self.assertNotIn("keep_words", calls[1])

    def test_dsl_pipeline_and_missing_narration_pass_cover(self):
        seen = {}

        def fake_text(*_args, **kwargs):
            seen.update(kwargs)
            raise llm.LlmError("stop")

        with patch.object(llm, "_narration_sample_cover", return_value=(["hooded"], ["baker"])), patch.object(
            llm, "build_dsl_user_prompt", return_value="prompt"
        ), patch.object(llm, "_chat_text", side_effect=fake_text):
            self.assertIsNone(llm._try_dsl_draft({}, "look", 30, [], []))
        self.assertEqual(seen["phase"], "draft_dsl")
        self.assertEqual(seen["hide_words"], ["hooded"])
        self.assertEqual(seen["keep_words"], ["baker"])

        seen.clear()

        def fake_para(*_args, **kwargs):
            seen.update(kwargs)
            return "The baker nods once."

        ledger = SimpleNamespace(
            forbidden_repeats=lambda: [],
            previously_attempted_texts=lambda _index: [],
        )
        with patch.object(llm, "_narration_sample_cover", return_value=(["hooded"], ["baker"])), patch.object(
            llm, "_chat_text", side_effect=fake_para
        ):
            writer = llm._make_pipeline_paragraph_writer([], None, 30, {})
            writer({"beat_index": 2, "model_limits": {}}, "", ledger)
        self.assertTrue(str(seen["phase"]).startswith("narration_para_"))
        self.assertEqual(seen["hide_words"], ["hooded"])
        self.assertEqual(seen["keep_words"], ["baker"])

        seen.clear()

        def fake_json(*_args, **kwargs):
            seen.update(kwargs)
            return {"narration": "kept"}

        with patch.object(llm, "_narration_sample_cover", return_value=(["hooded"], ["narration"])), patch.object(
            llm, "build_user_prompt", return_value="{}"
        ), patch.object(llm, "_chat_json", side_effect=fake_json):
            out = llm._retry_missing_narration(
                {},
                "look",
                "system",
                30,
                [],
                "draft_missing_narration_retry",
                [],
            )
        self.assertEqual(out["narration"], "kept")
        self.assertEqual(seen["phase"], "draft_missing_narration_retry")
        self.assertEqual(seen["hide_words"], ["hooded"])
        self.assertEqual(seen["keep_words"], ["narration"])

    def test_unlocked_forwards_hide_only_when_passed(self):
        with patch.dict(os.environ, {"AI_RPG_MODEL_PROVIDER": "mle"}), patch(
            "app.mle.chat", return_value="hello"
        ) as mocked:
            llm._chat_content_unlocked("system", "user", response_format=None)
            first = mocked.call_args.kwargs
            self.assertIsNone(first.get("hide_words"))
            self.assertIsNone(first.get("keep_words"))
            llm._chat_content_unlocked(
                "system",
                "user",
                hide_words=["hooded"],
                keep_words=["baker"],
            )
            second = mocked.call_args.kwargs
        self.assertEqual(second["hide_words"], ["hooded"])
        self.assertEqual(second["keep_words"], ["baker"])

    def test_player_agent_chat_stays_bare(self):
        tree = ast.parse((ROOT / "player_agent.py").read_text(encoding="utf-8"))
        found = False
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "mle_player_line":
                found = True
                for call in ast.walk(node):
                    if isinstance(call, ast.Call):
                        names = {kw.arg for kw in call.keywords}
                        self.assertNotIn("hide_words", names)
                        self.assertNotIn("keep_words", names)
        self.assertTrue(found)

    def test_draft_sites_pass_cover_and_other_calls_do_not(self):
        source = (ROOT / "app" / "llm.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        funcs = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        chat_calls = []
        for name, fn in funcs.items():
            for call in ast.walk(fn):
                if isinstance(call, ast.Call) and _call_name(call) in {"_chat_text", "_chat_json"}:
                    chat_calls.append((name, call))
        self.assertGreaterEqual(len(chat_calls), 8)
        seen_must = set()
        for name, call in chat_calls:
            phase = _phase_of(call)
            hidden = _has_hide(call)
            if phase in _BANNED_PHASES or (phase or "").startswith("setup_"):
                self.assertFalse(hidden, phase)
            if (phase or "").startswith("narration_para_"):
                self.assertTrue(hidden, phase)
            if name in _MUST_HIDE_FUNCS:
                self.assertTrue(hidden, name)
                seen_must.add(name)
            elif name == "_generate_turn_body":
                if phase in _DRAFT_PHASES:
                    self.assertTrue(hidden, phase)
                else:
                    self.assertFalse(hidden, phase or name)
            else:
                self.assertFalse(hidden, name)
        self.assertEqual(seen_must, _MUST_HIDE_FUNCS)
        draft_seen = set()
        for name, call in chat_calls:
            if name == "_generate_turn_body" and _phase_of(call) in _DRAFT_PHASES:
                draft_seen.add(_phase_of(call))
        self.assertEqual(draft_seen, _DRAFT_PHASES)

        json_fn = funcs["_chat_json"]
        content_calls = [
            call
            for call in ast.walk(json_fn)
            if isinstance(call, ast.Call) and _call_name(call) == "_chat_content"
        ]
        self.assertEqual(len(content_calls), 2)
        forwarded = [call for call in content_calls if _has_hide(call)]
        repairs = [
            call
            for call in content_calls
            if any(
                kw.arg == "temperature"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value == 0.0
                for kw in call.keywords
            )
        ]
        self.assertEqual(len(forwarded), 1)
        self.assertEqual(len(repairs), 1)
        self.assertFalse(_has_hide(repairs[0]))

        text_fn = funcs["_chat_text"]
        text_calls = [
            call
            for call in ast.walk(text_fn)
            if isinstance(call, ast.Call) and _call_name(call) == "_chat_content"
        ]
        self.assertEqual(len(text_calls), 1)
        self.assertTrue(_has_hide(text_calls[0]))

        unlocked = funcs["_chat_content_unlocked"]
        for call in ast.walk(unlocked):
            if not isinstance(call, ast.Call):
                continue
            if _call_name(call) == "mle_chat":
                self.assertTrue(_has_hide(call))
            if _call_name(call) == "_chat_content_openai_compatible":
                self.assertFalse(_has_hide(call))
        compatible = funcs["_chat_content_openai_compatible"]
        for node in ast.walk(compatible):
            if isinstance(node, ast.Name):
                self.assertNotIn(node.id, {"hide_words", "keep_words"})


if __name__ == "__main__":
    unittest.main()
