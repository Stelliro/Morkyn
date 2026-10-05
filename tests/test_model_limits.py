"""Token limits follow the model; the player's own numbers are kept per model.

Context window, soft response target and hard cap used to be one global each
(a launcher pref exported as env, a row in model_config). Switching from a 7B
to a 32B kept the 7B's numbers, and the launcher's first default of 8192
followed every model it ever met. app/model_limits.py resolves them per model:
explicit env > the player's saved numbers for that model > automatic from the
GGUF header (parameters, trained context, KV cost per token) and the GPU, or
a tokens-per-billion scale when only the name is known.

Run:  python -m unittest tests.test_model_limits
"""
from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-model-limits-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
    "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
    "AI_RPG_MODEL_LIMITS_NO_GPU": "1",
}
os.environ.update(_ENV)
for _name in ("AI_RPG_CONTEXT_TOKENS", "AI_RPG_LLAMA_CPP_CONTEXT", "AI_RPG_MAX_RESPONSE_TOKENS", "AI_RPG_RESPONSE_HARD_CAP_TOKENS", "AI_RPG_MAX_RESPONSE_HARD_CAP_TOKENS"):
    os.environ.pop(_name, None)

from app import db, launcher_prefs, llm, mle, model_limits  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


# --- a tiny GGUF writer: header only, the shape llama.cpp writes ------------
def _gguf_string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def write_gguf(path: Path, kv: dict[str, object], *, pad_bytes: int = 0) -> Path:
    out = bytearray(b"GGUF" + struct.pack("<IQQ", 3, 0, len(kv)))
    for key, value in kv.items():
        out += _gguf_string(key)
        if isinstance(value, bool):
            out += struct.pack("<I", 7) + struct.pack("<?", value)
        elif isinstance(value, int):
            out += struct.pack("<I", 4) + struct.pack("<I", value)
        elif isinstance(value, float):
            out += struct.pack("<I", 6) + struct.pack("<f", value)
        elif isinstance(value, str):
            out += struct.pack("<I", 8) + _gguf_string(value)
        elif isinstance(value, list):
            out += struct.pack("<I", 9) + struct.pack("<I", 8) + struct.pack("<Q", len(value))
            for item in value:
                out += _gguf_string(str(item))
        else:
            raise TypeError(type(value))
    out += b"\0" * pad_bytes
    path.write_bytes(bytes(out))
    return path


QWEN7B = {
    "general.architecture": "qwen2",
    "general.name": "Qwen2.5 7B Instruct",
    "general.size_label": "7B",
    "general.tags": ["chat", "text-generation"],
    "qwen2.block_count": 28,
    "qwen2.context_length": 32768,
    "qwen2.embedding_length": 3584,
    "qwen2.attention.head_count": 28,
    "qwen2.attention.head_count_kv": 4,
    "qwen2.rope.freq_base": 1000000.0,
}

GIB = 1024 ** 3


class TestGgufHeader(unittest.TestCase):
    def test_reads_the_facts_the_sizing_needs(self):
        path = write_gguf(_TMP / "qwen7b.gguf", QWEN7B, pad_bytes=4096)
        meta = model_limits.read_gguf_metadata(path)
        self.assertEqual(meta["general.architecture"], "qwen2")
        self.assertEqual(meta["qwen2.context_length"], 32768)
        self.assertEqual(meta["qwen2.attention.head_count_kv"], 4)
        self.assertNotIn("general.tags", meta, "arrays are skipped, not stored")
        facts = model_limits.model_facts({"provider": "mle", "gguf_model_path": str(path)})
        self.assertEqual(facts["kind"], "gguf")
        self.assertEqual(facts["params_b"], 7.0)
        self.assertEqual(facts["n_ctx_train"], 32768)
        # 2 (K+V) x 28 layers x 4 kv heads x 128 head_dim x 2 bytes
        self.assertEqual(facts["kv_bytes_per_token"], 57344)
        self.assertEqual(facts["key"], "gguf:qwen7b.gguf")

    def test_a_non_gguf_file_yields_name_facts_only(self):
        path = _TMP / "notgguf.gguf"
        path.write_bytes(b"not a model at all")
        facts = model_limits.model_facts({"provider": "mle", "gguf_model_path": str(path), "mle_model": "mystery-14b"})
        self.assertEqual(facts["kind"], "file")
        self.assertEqual(facts["params_b"], 14.0)
        self.assertNotIn("n_ctx_train", facts)

    def test_the_header_is_cached_by_size_and_mtime(self):
        path = write_gguf(_TMP / "cached.gguf", QWEN7B)
        first = model_limits.read_gguf_metadata(path)
        with mock.patch.object(model_limits, "_parse_gguf_header", side_effect=AssertionError("should be cached")):
            again = model_limits.read_gguf_metadata(path)
        self.assertEqual(first, again)


class TestParameterCountFromText(unittest.TestCase):
    def test_names_and_labels(self):
        self.assertEqual(model_limits.params_from_text("qwen3:8b"), 8.0)
        self.assertEqual(model_limits.params_from_text("Meta-Llama-3.1-70B-Instruct-Q4_K_M"), 70.0)
        self.assertEqual(model_limits.params_from_text("phi-3.5-mini"), None)
        self.assertEqual(model_limits.params_from_text("1.5B"), 1.5)
        self.assertEqual(model_limits.params_from_text("q4_k_m"), None)


class TestAutomaticLimits(unittest.TestCase):
    def _facts(self, **extra):
        base = {"kind": "gguf", "params_b": 7.0, "n_ctx_train": 32768, "kv_bytes_per_token": 57344, "file_bytes": int(4.4 * GIB)}
        base.update(extra)
        return base

    def test_the_whole_trained_context_fits_on_a_12gb_card(self):
        facts = self._facts(n_ctx_train=16384)
        context, why = model_limits.auto_context_tokens(facts, {"total_bytes": 12 * GIB, "free_bytes": 10 * GIB})
        self.assertEqual(context, 16384)
        self.assertIn("trained to 16,384", why)

    def test_a_roomy_card_stops_at_the_auto_ceiling(self):
        # Playtest #36: more than a turn needs only costs memory and prompt time.
        context, why = model_limits.auto_context_tokens(self._facts(), {"total_bytes": 12 * GIB, "free_bytes": 10 * GIB})
        self.assertEqual(context, model_limits.AUTO_CONTEXT_CEILING)
        self.assertIn("capped at", why)

    def test_a_big_model_on_a_small_card_gets_what_the_cache_allows(self):
        # 32B weights at 18 GB on a 24 GB card: ~4.3 GB left for cache at 160 KB per token.
        facts = self._facts(params_b=32.0, kv_bytes_per_token=163840, file_bytes=18 * GIB, n_ctx_train=131072)
        context, why = model_limits.auto_context_tokens(facts, {"total_bytes": 24 * GIB, "free_bytes": 20 * GIB})
        self.assertGreaterEqual(context, model_limits.MIN_CONTEXT_TOKENS)
        self.assertLess(context, 32768)
        self.assertEqual(context % model_limits.CONTEXT_STEP, 0)
        self.assertIn("fit beside", why)

    def test_weights_larger_than_the_card_floor_at_the_minimum(self):
        facts = self._facts(file_bytes=40 * GIB)
        context, _ = model_limits.auto_context_tokens(facts, {"total_bytes": 12 * GIB, "free_bytes": 1 * GIB})
        self.assertEqual(context, model_limits.MIN_CONTEXT_TOKENS)

    def test_without_a_gpu_the_tokens_per_billion_scale_decides(self):
        seven, _ = model_limits.auto_context_tokens({"params_b": 7.0}, None)
        fourteen, _ = model_limits.auto_context_tokens({"params_b": 14.0}, None)
        seventy, why = model_limits.auto_context_tokens({"params_b": 70.0}, None)
        self.assertEqual(seven, 32768)
        self.assertEqual(fourteen, 18432)
        self.assertEqual(seventy, model_limits.NO_FACTS_CONTEXT_FLOOR)
        self.assertIn("tokens-per-billion", why)

    def test_the_trained_context_caps_the_scale(self):
        context, _ = model_limits.auto_context_tokens({"params_b": 3.0, "n_ctx_train": 8192}, None)
        self.assertEqual(context, 8192)

    def test_nothing_known_means_the_default_window(self):
        context, why = model_limits.auto_context_tokens({}, None)
        self.assertEqual(context, model_limits.DEFAULT_CONTEXT_TOKENS)
        self.assertIn("nothing is known", why)

    def test_response_caps_scale_with_parameters(self):
        self.assertEqual(model_limits.auto_response_caps({"params_b": 3.0})[:2], (1200, 1600))
        self.assertEqual(model_limits.auto_response_caps({"params_b": 8.0})[:2], (1500, 2000))
        self.assertEqual(model_limits.auto_response_caps({"params_b": 14.0})[:2], (1800, 2400))
        self.assertEqual(model_limits.auto_response_caps({"params_b": 70.0})[:2], (2000, 2600))
        self.assertEqual(model_limits.auto_response_caps({"kind": "api", "params_b": None})[:2], model_limits.API_RESPONSE_CAPS)
        self.assertEqual(model_limits.auto_response_caps({})[:2], model_limits.DEFAULT_RESPONSE_CAPS)


class TestRememberedPerModel(unittest.TestCase):
    def setUp(self):
        self.seven = write_gguf(_TMP / "seven.gguf", QWEN7B)
        fourteen = dict(QWEN7B, **{"general.name": "Big 14B", "general.size_label": "14B", "qwen2.block_count": 48, "qwen2.embedding_length": 5120, "qwen2.attention.head_count": 40, "qwen2.attention.head_count_kv": 8})
        self.fourteen = write_gguf(_TMP / "fourteen.gguf", fourteen)
        for key in ("gguf:seven.gguf", "gguf:fourteen.gguf"):
            model_limits.set_limits(key, None)

    def _cfg(self, path):
        return {"provider": "mle", "gguf_model_path": str(path), "mle_model": "x"}

    def test_auto_is_the_default_and_names_its_source(self):
        resolved = model_limits.resolve_limits(self._cfg(self.seven))
        self.assertEqual(resolved["mode"], "auto")
        self.assertEqual(resolved["context_tokens"], 32768)
        self.assertEqual(resolved["source"], {"context_tokens": "auto", "response_token_cap": "auto", "response_token_hard_cap": "auto"})
        self.assertEqual(resolved["label"], "Qwen2.5 7B Instruct")

    def test_custom_numbers_stick_to_their_model_and_not_to_another(self):
        model_limits.set_limits("gguf:seven.gguf", {"context_tokens": 16384, "response_token_cap": 900, "response_token_hard_cap": 1200})
        seven = model_limits.resolve_limits(self._cfg(self.seven))
        self.assertEqual(seven["mode"], "custom")
        self.assertEqual((seven["context_tokens"], seven["response_token_cap"], seven["response_token_hard_cap"]), (16384, 900, 1200))
        self.assertEqual(seven["source"]["context_tokens"], "custom")
        fourteen = model_limits.resolve_limits(self._cfg(self.fourteen))
        self.assertEqual(fourteen["mode"], "auto", "the other model keeps its automatic numbers")
        self.assertEqual(fourteen["response_token_cap"], 1800)

    def test_switching_away_and_back_restores_the_saved_numbers(self):
        model_limits.set_limits("gguf:seven.gguf", {"context_tokens": 20480})
        model_limits.resolve_limits(self._cfg(self.fourteen))
        again = model_limits.resolve_limits(self._cfg(self.seven))
        self.assertEqual(again["context_tokens"], 20480)
        # A field left out of the custom entry still comes from auto.
        self.assertEqual(again["source"]["response_token_cap"], "auto")

    def test_forgetting_returns_to_auto(self):
        model_limits.set_limits("gguf:seven.gguf", {"context_tokens": 20480})
        model_limits.set_limits("gguf:seven.gguf", None)
        self.assertEqual(model_limits.resolve_limits(self._cfg(self.seven))["mode"], "auto")

    def test_custom_values_are_clamped_and_ordered(self):
        entry = model_limits.set_limits("gguf:seven.gguf", {"context_tokens": 99, "response_token_cap": 3000, "response_token_hard_cap": 100})
        self.assertEqual(entry["context_tokens"], model_limits.MIN_CONTEXT_TOKENS)
        self.assertEqual(entry["response_token_hard_cap"], 3000, "the hard cap is never below the soft target")

    def test_explicit_env_outranks_both(self):
        model_limits.set_limits("gguf:seven.gguf", {"context_tokens": 20480})
        with mock.patch.dict(os.environ, {"AI_RPG_CONTEXT_TOKENS": "12288"}):
            resolved = model_limits.resolve_limits(self._cfg(self.seven))
        self.assertEqual(resolved["context_tokens"], 12288)
        self.assertEqual(resolved["source"]["context_tokens"], "env")
        with mock.patch.dict(os.environ, {"AI_RPG_CONTEXT_TOKENS": "auto"}):
            resolved = model_limits.resolve_limits(self._cfg(self.seven))
        self.assertEqual(resolved["context_tokens"], 20480, "the word auto in the env is not a number")


class TestTheConfigCarriesTheLimits(unittest.TestCase):
    def setUp(self):
        self.seven = write_gguf(_TMP / "cfg-seven.gguf", QWEN7B)
        model_limits.set_limits("gguf:cfg-seven.gguf", None)
        llm.update_model_config({"provider": "mle", "gguf_model_path": str(self.seven), "mle_model": "x"})

    def test_get_model_config_resolves_caps_and_window(self):
        cfg = llm.get_model_config(ignore_override=True)
        self.assertEqual(cfg["context_window"], 32768)
        self.assertEqual(cfg["response_token_cap"], 1500)
        self.assertEqual(cfg["model_limits"]["mode"], "auto")
        self.assertEqual(llm.context_window_tokens(cfg), 32768)
        self.assertEqual(llm._response_token_settings(cfg), (1500, 2000))

    def test_saving_the_form_as_custom_remembers_this_model(self):
        public = llm.update_model_config({"limits_mode": "custom", "context_tokens": 16384, "response_token_cap": 1000, "response_token_hard_cap": 1400})
        self.assertEqual(public["limits"]["mode"], "custom")
        self.assertEqual(public["context_window"], 16384)
        self.assertEqual(public["response_token_cap"], 1000)
        self.assertEqual(llm.context_window_tokens(), 16384)
        stored = model_limits.stored_limits("gguf:cfg-seven.gguf")
        self.assertEqual(stored["context_tokens"], 16384)

    def test_saving_as_auto_forgets_them(self):
        llm.update_model_config({"limits_mode": "custom", "context_tokens": 16384})
        public = llm.update_model_config({"limits_mode": "auto"})
        self.assertEqual(public["limits"]["mode"], "auto")
        self.assertEqual(public["context_window"], 32768)

    def test_the_overlay_is_not_written_into_the_stored_config(self):
        llm.update_model_config({"limits_mode": "custom", "context_tokens": 16384})
        with db.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'model_config'").fetchone()
        self.assertNotIn("context_window", row["value"])
        self.assertNotIn("model_limits", row["value"])

    def test_mle_opens_the_model_with_the_resolved_window(self):
        llm.update_model_config({"limits_mode": "custom", "context_tokens": 20480})
        self.assertEqual(mle._context_tokens(), 20480)
        with mock.patch.dict(os.environ, {"AI_RPG_CONTEXT_TOKENS": "8192"}):
            self.assertEqual(mle._context_tokens(), 8192, "explicit env still wins")

    def test_a_changed_window_reopens_the_same_file(self):
        opened = []

        def fake_open(path, n_ctx):
            opened.append(n_ctx)
            return mock.Mock()

        with mock.patch.object(mle, "_open_model", side_effect=fake_open), mock.patch.object(mle, "_close_quiet"):
            mle._drop_model()
            with mock.patch.object(mle, "_context_tokens", return_value=32768):
                mle._ensure_loaded(self.seven)
                mle._ensure_loaded(self.seven)
            with mock.patch.object(mle, "_context_tokens", return_value=16384):
                mle._ensure_loaded(self.seven)
            # The accepted fallback size stands against a bigger request.
            with mock.patch.object(mle, "_MODEL_CTX", mle._FALLBACK_CONTEXT), mock.patch.object(mle, "_context_tokens", return_value=32768):
                mle._ensure_loaded(self.seven)
            mle._drop_model()
        self.assertEqual(opened, [32768, 16384])


class TestLauncherPrefsAuto(unittest.TestCase):
    def test_auto_is_the_default_and_exports_no_env(self):
        prefs = launcher_prefs.default_prefs()
        self.assertEqual(prefs["llama_cpp_context"], "auto")
        self.assertEqual(prefs["soft_response_tokens"], 0)
        with mock.patch.dict(os.environ, {"AI_RPG_CONTEXT_TOKENS": "8192"}):
            launcher_prefs.apply_prefs_to_env(prefs)
            self.assertNotIn("AI_RPG_CONTEXT_TOKENS", os.environ)
            launcher_prefs.apply_prefs_to_env(dict(prefs, llama_cpp_context=24576))
            self.assertEqual(os.environ["AI_RPG_CONTEXT_TOKENS"], "24576")

    def test_explicit_pref_int(self):
        for raw, expect in (("auto", 0), ("", 0), (None, 0), ("8192", 8192), (8192, 8192), ("0", 0), ("-5", 0), ("x", 0), (16384.0, 16384)):
            self.assertEqual(launcher_prefs.explicit_pref_int(raw), expect, raw)

    def test_the_powershell_launcher_agrees(self):
        ps1 = (ROOT / "Morkyn.ps1").read_text(encoding="utf-8", errors="replace")
        self.assertIn('llama_cpp_context        = "auto"', ps1)
        self.assertIn("Get-AutoContextTokens", ps1)
        self.assertIn("app.model_limits", ps1)


class TestCommandLine(unittest.TestCase):
    def test_context_for_a_file(self):
        path = write_gguf(_TMP / "cli.gguf", QWEN7B)
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = model_limits._main(["--context", str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue().strip(), "32768")


if __name__ == "__main__":
    unittest.main()
