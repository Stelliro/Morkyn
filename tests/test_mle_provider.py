"""MLE is the local provider. It loads a GGUF in-process."""
from __future__ import annotations

import ast
import os
import sqlite3
import sys
import tempfile
import threading
import time
import types
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
from app import mle
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

    def test_a_named_model_that_is_missing_is_missing(self):
        from app.mle import substitution_note

        only = self.models / "qwen2.5-7b-instruct-q4_k_m.gguf"
        only.write_bytes(b"GGUF")
        # The default name may stand in for the only file, and says so.
        self.assertEqual(resolve_model_path("qwen3:8b"), only)
        self.assertIn("qwen2.5-7b-instruct-q4_k_m.gguf", substitution_note("qwen3:8b"))
        # Anything the player actually named is not swapped for another file.
        self.assertIsNone(resolve_model_path("qwen3-14b"))
        self.assertIsNone(resolve_model_path(str(Path(self._tmp.name) / "gone.gguf")))
        with patch.dict(os.environ, {"MLE_MODEL": str(Path(self._tmp.name) / "gone.gguf")}):
            self.assertIsNone(resolve_model_path("qwen3:8b"))
            self.assertFalse(status("qwen3:8b")["ok"])
        # A file whose name matches needs no note.
        self.assertEqual(substitution_note("qwen2.5-7b-instruct-q4_k_m"), "")

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


class TestStatusDoesNotWaitOnGeneration(unittest.TestCase):
    """status() used to take _LOCK unconditionally, so Test Connection and the
    context-fallback endpoint parked behind an in-flight turn for up to the
    MLE timeout. When the model is already loaded for the resolved path the
    lock buys nothing; when it is not, status waits briefly and reports busy."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.models = Path(self._tmp.name) / "models"
        self.models.mkdir()
        self.gguf = self.models / "only.gguf"
        self.gguf.write_bytes(b"GGUF")
        self._env = patch.dict(os.environ, {"MLE_MODEL": "", "MLE_GGUF": ""})
        self._dir = patch("app.mle.models_dir", return_value=self.models)
        self._env.start()
        self._dir.start()
        self.assertTrue(mle._LOCK.acquire(timeout=1), "test needs the lock")

    def tearDown(self):
        mle._LOCK.release()
        self._dir.stop()
        self._env.stop()
        self._tmp.cleanup()

    def _status_in_thread(self, wait: float = 3.0):
        box = {}

        def run():
            box["report"] = status("only")

        worker = threading.Thread(target=run, daemon=True)
        started = time.monotonic()
        worker.start()
        worker.join(wait)
        return box.get("report"), time.monotonic() - started, worker.is_alive()

    def test_loaded_model_reports_without_the_lock(self):
        with patch.object(mle, "_MODEL", object()), patch.object(
            mle, "_MODEL_PATH", str(self.gguf.resolve())
        ), patch.object(mle, "_MODEL_CTX", 8192), patch.object(mle, "_DETAIL", "Loaded only.gguf in-process (context 8192)."):
            report, elapsed, alive = self._status_in_thread()
        self.assertFalse(alive, "status must not park behind the generation lock")
        self.assertLess(elapsed, 2.5)
        self.assertTrue(report["ok"])
        self.assertEqual(report["context"], 8192)
        self.assertIn("only.gguf", report["detail"])

    def test_unloaded_model_reports_busy_instead_of_waiting(self):
        with patch.object(mle, "_MODEL", None), patch.object(mle, "_MODEL_PATH", ""), patch.object(
            mle, "_STATUS_LOCK_WAIT", 0.1
        ), patch.object(mle, "_ensure_loaded", side_effect=AssertionError("must not load while busy")):
            report, elapsed, alive = self._status_in_thread()
        self.assertFalse(alive)
        self.assertLess(elapsed, 2.0)
        self.assertFalse(report["ok"])
        self.assertTrue(report["busy"])
        self.assertIn("generating", report["detail"])

    def test_lock_is_released_after_a_failed_load(self):
        mle._LOCK.release()
        try:
            with patch.object(mle, "_MODEL", None), patch.object(mle, "_MODEL_PATH", ""), patch.object(
                mle, "_ensure_loaded", side_effect=MleNotReady("MLE could not load only.gguf.")
            ):
                report = status("only")
            self.assertFalse(report["ok"])
            self.assertIn("could not load", report["detail"])
            self.assertTrue(mle._LOCK.acquire(blocking=False), "status left the lock held")
            mle._LOCK.release()
        finally:
            self.assertTrue(mle._LOCK.acquire(timeout=1))


def _fake_llama_module():
    """The real llama_cpp when installed; else a stand-in exposing LogitsProcessorList."""
    try:
        import llama_cpp.llama  # noqa: F401

        return None
    except Exception:
        pkg = types.ModuleType("llama_cpp")
        sub = types.ModuleType("llama_cpp.llama")
        sub.LogitsProcessorList = list
        pkg.llama = sub
        return {"llama_cpp": pkg, "llama_cpp.llama": sub}


class _FakeModel:
    """create_chat_completion runs the logits processor once, optionally past the deadline."""

    def __init__(self, text: str, expire: bool):
        self.text = text
        self.expire = expire
        self.calls = 0

    def token_eos(self):
        return 2

    def create_chat_completion(self, **kwargs):
        import numpy as np

        self.calls += 1
        processor = kwargs.get("logits_processor")
        if processor:
            mask = processor[0]
            if self.expire:
                mask.deadline = time.monotonic() - 1
            mask(None, np.zeros(4, dtype=np.float32))
        return {"choices": [{"message": {"content": self.text}}]}


class TestGenerationTimeoutIsAnError(unittest.TestCase):
    """The per-call timeout forced EOS silently, so a 300s stall came back as a
    normal truncated completion: no timeout guard in llm.py or the failsafe
    could see it, and a half JSON draft went on to repair or parse."""

    def setUp(self):
        self._modules = _fake_llama_module()
        self._patch = patch.dict(sys.modules, self._modules) if self._modules else None
        if self._patch:
            self._patch.start()

    def tearDown(self):
        if self._patch:
            self._patch.stop()

    def test_sample_mask_records_the_deadline_hit(self):
        import numpy as np

        mask = mle._SampleMask(np.asarray([], dtype=np.int32), time.monotonic() - 1, 2)
        self.assertFalse(mask.hit)
        out = mask(None, np.zeros(4, dtype=np.float32))
        self.assertTrue(mask.hit)
        self.assertEqual(float(out[2]), 0.0)
        self.assertTrue(all(np.isneginf(out[i]) for i in (0, 1, 3)))

        fresh = mle._SampleMask(np.asarray([], dtype=np.int32), time.monotonic() + 60, 2)
        fresh(None, np.zeros(4, dtype=np.float32))
        self.assertFalse(fresh.hit)

    def test_generate_raises_a_timeout_the_guards_recognise(self):
        model = _FakeModel('{"narration": "half a', expire=True)
        with patch.object(mle, "_banned_ids", return_value=()):
            with self.assertRaises(MleNotReady) as caught:
                mle._generate(
                    model, "x.gguf", "sys", "user", timeout=7, temperature=0.7,
                    max_tokens=None, response_format="json", hide_words=None, keep_words=None,
                )
        message = str(caught.exception)
        self.assertIn("timed out after 7s", message)
        self.assertEqual(model.calls, 1)
        wrapped = llm.LlmError(message)
        self.assertTrue(llm._is_timeout_error(wrapped))
        self.assertTrue(llm._is_model_unavailable_error(wrapped))
        self.assertEqual(llm._transport_error_message(wrapped, 7), "timed out after 7s")
        from app.failsafe import classify_failure

        self.assertEqual(classify_failure(message, stage="turn", provider="mle")["code"], "timeout")

    def test_generate_returns_text_when_the_deadline_did_not_fire(self):
        model = _FakeModel('{"narration": "whole"}', expire=False)
        with patch.object(mle, "_banned_ids", return_value=()):
            out = mle._generate(
                model, "x.gguf", "sys", "user", timeout=7, temperature=0.7,
                max_tokens=None, response_format="json", hide_words=None, keep_words=None,
            )
        self.assertEqual(out, '{"narration": "whole"}')


if __name__ == "__main__":
    unittest.main()
