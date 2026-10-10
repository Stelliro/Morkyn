"""Text to speech for the narration (TODO n24): cleaning, chunking, config, routes.

Everything that would leave the machine is mocked: the cloud transport
(``app.tts._http`` / ``urllib.request.urlopen``), ``pip`` and the ``piper`` import.

Run:  python -m unittest tests.test_tts
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
import wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-tts-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_CONSOLIDATED_FACTS": str(_TMP / "facts.jsonl"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
    "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
    "AI_RPG_TTS_VOICE_DIR": str(_TMP / "tts-voices"),
    # The gate test needs "llm busy" to block "tts" regardless of the machine's GPU.
    "AI_RPG_GPU_FORCE_SERIAL": "1",
}
os.environ.update(_ENV)

from fastapi.testclient import TestClient  # noqa: E402

import app.gpu_gate as gpu_gate  # noqa: E402
import app.tts as tts  # noqa: E402
from app.db import connect, db_path, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.world import get_state  # noqa: E402

_ORIGINAL_PIPER = sys.modules.get("piper", "<absent>")
_KEY_ENVS = ("AI_RPG_TTS_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "ELEVEN_API_KEY")


def _assert_isolated() -> None:
    for label, value in (("AI_RPG_DB", db_path()), ("AI_RPG_TTS_VOICE_DIR", tts.voice_dir())):
        if not str(value).startswith(str(_TMP)):
            raise AssertionError(f"test isolation failed: {label} resolves to {value!r}")


def setUpModule() -> None:
    """Re-pin paths: unittest imports every test module before running any test."""
    os.environ.update(_ENV)
    _assert_isolated()
    init_db()


_assert_isolated()
init_db()


def _clear_tts_env() -> None:
    for key in list(os.environ):
        if key.startswith("AI_RPG_TTS_") and key != "AI_RPG_TTS_VOICE_DIR":
            del os.environ[key]
    for key in _KEY_ENVS:
        os.environ.pop(key, None)


def _restore_piper_module() -> None:
    if _ORIGINAL_PIPER == "<absent>":
        sys.modules.pop("piper", None)
    else:
        sys.modules["piper"] = _ORIGINAL_PIPER


def _write_fake_voice(code: str, *, sample_rate: int | None = 22050) -> None:
    onnx, meta = tts.piper_voice_paths(code)
    onnx.parent.mkdir(parents=True, exist_ok=True)
    onnx.write_bytes(b"\0" * (tts.PIPER_MIN_ONNX_BYTES + 16))
    payload = {"audio": {"sample_rate": sample_rate}} if sample_rate else {"audio": {}}
    meta.write_text(json.dumps(payload), encoding="utf-8")


def _remove_fake_voice(code: str) -> None:
    for path in tts.piper_voice_paths(code):
        try:
            path.unlink()
        except OSError:
            pass


class _FakeChunk:
    def __init__(self, sample_rate: int, seconds: float = 2.0):
        self.sample_rate = sample_rate
        self.sample_width = 2
        self.sample_channels = 1
        self.audio_int16_bytes = b"\0" * int(sample_rate * seconds) * 2


def _fake_piper_module(calls: dict) -> types.ModuleType:
    module = types.ModuleType("piper")

    class SynthesisConfig:
        def __init__(self, speaker_id=None, length_scale=None, noise_scale=None, noise_w_scale=None,
                     normalize_audio=True, volume=1.0):
            self.length_scale = length_scale
            calls["length_scale"] = length_scale

    class _Voice:
        def __init__(self):
            self.config = types.SimpleNamespace(sample_rate=22050)

        def synthesize(self, text, syn_config=None):
            calls.setdefault("texts", []).append(text)
            yield _FakeChunk(self.config.sample_rate)

    class PiperVoice:
        @staticmethod
        def load(model_path, config_path=None, **kwargs):
            calls["load"] = (str(model_path), str(config_path))
            return _Voice()

    module.SynthesisConfig = SynthesisConfig
    module.PiperVoice = PiperVoice
    return module


class _FakeResponse(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class TtsCase(unittest.TestCase):
    """Shared setup: no env overrides, no stored row, no cached voice, real piper import state."""

    def setUp(self):
        os.environ.update(_ENV)
        _clear_tts_env()
        with connect() as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (tts.TTS_CONFIG_KEY,))
        tts._piper_voice_cache.clear()
        _restore_piper_module()
        self.client = TestClient(app)

    def tearDown(self):
        _clear_tts_env()
        _restore_piper_module()
        tts._piper_voice_cache.clear()
        for row in tts._PIPER_VOICES:
            _remove_fake_voice(row["code"])


# --- 1. cleaning ------------------------------------------------------------


class TestCleanText(TtsCase):
    def test_codes_markup_and_debug_lines_are_removed(self):
        raw = (
            "[[L1]] The **tavern** was *quiet*, `almost` too quiet.\n"
            "MOVE L2\n"
            "QUEST_DONE Q1\n"
            '{ "x": 1 }\n'
            "// note to self\n"
            "[debug] trace line\n"
            "# Heading\n"
            "> quoted\n"
            "- bullet\n"
            "<b>Mara</b> &amp; Jo waited at E3 near [[N12]] with I2.\n"
            "I went to the door. NO! Not again."
        )
        out = tts.clean_text(raw)
        for gone in ("[[", "]]", "**", "`", "MOVE", "QUEST_DONE", '"x"', "// note", "[debug]", "<b>", "&amp;",
                     "L1", "E3", "N12", "I2", "Heading", "- bullet", "> quoted"):
            self.assertNotIn(gone, out, msg=f"{gone!r} should be stripped: {out!r}")
        self.assertIn("The tavern was quiet, almost too quiet.", out)
        self.assertIn("Mara & Jo waited at near with.", out)
        self.assertIn("I went to the door. NO! Not again.", out)
        # List and quote markers go; the words after them are read.
        self.assertIn("\nquoted\nbullet\n", out)

    def test_prose_starting_with_capitals_or_brackets_is_kept(self):
        self.assertEqual(
            tts.clean_text("YOU are the one the prophecy named. The crowd parts."),
            "YOU are the one the prophecy named. The crowd parts.",
        )
        self.assertEqual(tts.clean_text("WAIT here, she said.\nShe waited."), "WAIT here, she said.\nShe waited.")
        self.assertEqual(tts.clean_text("#3 on the list was gone."), "#3 on the list was gone.")
        self.assertEqual(tts.clean_text("[The torch gutters.] Darkness."), "[The torch gutters.] Darkness.")
        self.assertEqual(tts.clean_text("$5 was all he had."), "$5 was all he had.")
        # Real ops, quoted arguments, JSON and markers still go.
        self.assertEqual(tts.clean_text('TALK "Mara"\nLEAD L2\n@NAR\n["a", 1]\n{\n}\nShe nods.'), "She nods.")

    def test_inline_op_and_code_pairs_go_together(self):
        # The line rule only sees ops at the start of a line; "creaks. MOVE L2" mid-line
        # must not leave the word MOVE behind.
        self.assertEqual(tts.clean_text("The door creaks. MOVE L2\nShe waits. E3"), "The door creaks.\nShe waits.")
        self.assertEqual(tts.clean_text("I said NO! Not again. HELP me."), "I said NO! Not again. HELP me.")

    def test_code_only_input_is_empty(self):
        self.assertEqual(tts.clean_text("[[A]] [[L1]] L1 I2 E3"), "")
        self.assertEqual(tts.clean_text("   \n\n "), "")
        self.assertEqual(tts.clean_text(""), "")

    def test_whitespace_collapses_and_entities_unescape(self):
        self.assertEqual(tts.clean_text("Rain\t\tfell   hard.&nbsp;It&#39;s late…"), "Rain fell hard. It's late...")
        self.assertEqual(tts.clean_text("One.\n\n\n\nTwo."), "One.\n\nTwo.")

    def test_names_and_contractions_survive(self):
        out = tts.clean_text("Ser Aldric_of_Vane said 'tis time. The snake_case word stays. 2nd gate, B2 is gone.")
        self.assertIn("Aldric_of_Vane", out)
        self.assertIn("snake_case", out)
        self.assertIn("2nd gate", out)
        self.assertNotIn("B2", out)

    def test_markdown_links_and_urls(self):
        out = tts.clean_text("See [the map](https://example.com/map) or https://example.com now.")
        self.assertEqual(out, "See the map or now.")

    def test_paragraph_starting_with_code_block_is_kept(self):
        self.assertEqual(tts.clean_text("[[L1]]The tavern was quiet."), "The tavern was quiet.")


# --- 2. chunking ------------------------------------------------------------


class TestChunking(TtsCase):
    def test_split_paragraphs(self):
        self.assertEqual(tts.split_paragraphs("One.\n\nTwo.\nThree. [[L1]]"), ["One.", "Two.", "Three."])
        self.assertEqual(tts.split_paragraphs("[[A]]"), [])
        many = "\n".join(f"Line {i}." for i in range(80))
        self.assertEqual(len(tts.split_paragraphs(many)), 60)

    def test_chunk_text_prefers_sentence_ends(self):
        text = "First sentence here. Second one follows! Third asks? " * 20
        chunks = tts.chunk_text(text, 200)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 200)
            self.assertTrue(chunk.rstrip().endswith((".", "!", "?")), chunk)
        self.assertEqual(" ".join(chunks), " ".join(text.split()))

    def test_chunk_text_hard_cuts_without_spaces(self):
        text = "x" * 1200
        chunks = tts.chunk_text(text, 500)
        self.assertEqual([len(c) for c in chunks], [500, 500, 200])
        self.assertEqual("".join(chunks), text)

    def test_chunk_text_clamps_limit(self):
        text = "word " * 100
        chunks = tts.chunk_text(text, 10)
        self.assertTrue(all(len(c) <= 200 for c in chunks))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(tts.chunk_text("short", 50), ["short"])
        self.assertEqual(tts.chunk_text("   ", 300), [])

    def test_chunk_text_falls_back_to_clauses_and_words(self):
        text = ("clause one, clause two; clause three: " * 12).strip()
        chunks = tts.chunk_text(text, 200)
        self.assertTrue(all(len(c) <= 200 for c in chunks))
        self.assertEqual(" ".join(chunks), " ".join(text.split()))


# --- 3. defaults / env / masking -------------------------------------------


class TestConfig(TtsCase):
    def test_defaults(self):
        self.assertEqual(tts.get_tts_config(), {
            "provider": "off", "enabled": False, "preset": "", "voice": "", "model": "", "base_url": "",
            "api_key": "", "speed": 1.0, "chunk_chars": 0, "timeout_seconds": 60,
        })
        self.assertFalse(tts.tts_active())

    def test_stored_row_merges_and_env_wins(self):
        tts.update_tts_config({"provider": "piper", "enabled": True, "speed": 1.5})
        cfg = tts.get_tts_config()
        self.assertEqual((cfg["provider"], cfg["enabled"], cfg["speed"]), ("piper", True, 1.5))
        os.environ["AI_RPG_TTS_PROVIDER"] = "elevenlabs"
        self.assertEqual(tts.get_tts_config()["provider"], "elevenlabs")

    def test_alias_normalisation_and_clamps(self):
        for raw, want in (("local", "piper"), ("custom", "openai"), ("11labs", "elevenlabs"), ("none", "off"),
                          ("", "off"), ("bogus", "off"), ("Eleven", "elevenlabs")):
            self.assertEqual(tts.normalize_provider(raw), want)
        tts.update_tts_config({"provider": "local", "speed": 9, "chunk_chars": 50, "timeout_seconds": 1})
        cfg = tts.get_tts_config()
        self.assertEqual((cfg["provider"], cfg["speed"], cfg["chunk_chars"], cfg["timeout_seconds"]),
                         ("piper", 2.0, 200, 5))
        os.environ["AI_RPG_TTS_SPEED"] = "nan"
        self.assertEqual(tts.get_tts_config()["speed"], 1.0)

    def test_base_url_normalisation(self):
        self.assertEqual(tts.normalize_base_url("http://127.0.0.1:8880/v1/"), "http://127.0.0.1:8880")
        self.assertEqual(tts.normalize_base_url("https://api.openai.com/"), "https://api.openai.com")
        self.assertEqual(tts.normalize_base_url("ftp://x"), "")
        self.assertEqual(tts.normalize_base_url("api.openai.com"), "")

    def test_public_view_masks_the_key(self):
        tts.update_tts_config({"provider": "openai", "api_key": "sk-secret-1234"})
        public = tts.public_tts_config()
        self.assertEqual(public["api_key"], "")
        self.assertTrue(public["api_key_set"])
        self.assertEqual(public["api_key_hint"], "••••1234")
        self.assertEqual(public["key_env"], "OPENAI_API_KEY")
        self.assertFalse(public["active"])
        self.assertEqual(public["resolved"]["preset"], "openai_gpt4o_mini_tts")
        self.assertEqual(public["resolved"]["voice"], "coral")
        self.assertEqual(public["resolved"]["model"], "gpt-4o-mini-tts")
        self.assertEqual(public["resolved"]["base_url"], "https://api.openai.com")
        self.assertEqual(public["resolved"]["chunk_chars"], 4000)
        self.assertEqual(public["resolved"]["audio_format"], "mp3")
        self.assertEqual(public["voice"], "", "stored blanks stay blank so the UI can show 'from preset'")
        self.assertTrue(public["voice_dir"].startswith(str(_TMP)))
        self.assertNotIn("sk-secret", json.dumps(public))

    def test_key_fallbacks(self):
        tts.update_tts_config({"provider": "elevenlabs"})
        self.assertEqual(tts.resolve_tts_api_key(), "")
        os.environ["ELEVEN_API_KEY"] = "e1"
        self.assertEqual(tts.resolve_tts_api_key(), "e1")
        os.environ["ELEVENLABS_API_KEY"] = "e2"
        self.assertEqual(tts.resolve_tts_api_key(), "e2")
        os.environ["AI_RPG_TTS_API_KEY"] = "e3"
        self.assertEqual(tts.resolve_tts_api_key(), "e3")
        self.assertEqual(tts.public_tts_config()["api_key_hint"], "••••")
        tts.update_tts_config({"provider": "piper"})
        self.assertEqual(tts.resolve_tts_api_key(), "", "piper never needs a key")

    def test_blank_key_keeps_stored_and_preset_change_resets(self):
        tts.update_tts_config({"provider": "openai", "api_key": "sk-keepme", "voice": "fable", "model": "tts-1"})
        tts.update_tts_config({"api_key": ""})
        self.assertEqual(tts.get_tts_config()["api_key"], "sk-keepme")
        tts.update_tts_config({"speed": 1.2})
        cfg = tts.get_tts_config()
        self.assertEqual((cfg["voice"], cfg["model"]), ("fable", "tts-1"), "a partial post keeps other keys")
        tts.update_tts_config({"preset": "openai_tts1"})
        cfg = tts.get_tts_config()
        self.assertEqual((cfg["preset"], cfg["voice"], cfg["model"], cfg["base_url"]), ("openai_tts1", "", "", ""))
        tts.update_tts_config({"preset": "openai_compatible", "voice": "bella", "base_url": "http://127.0.0.1:8880/v1"})
        cfg = tts.get_tts_config()
        self.assertEqual((cfg["voice"], cfg["base_url"]), ("bella", "http://127.0.0.1:8880"))
        tts.update_tts_config({"provider": "elevenlabs"})
        cfg = tts.get_tts_config()
        self.assertEqual((cfg["provider"], cfg["preset"], cfg["voice"], cfg["base_url"]), ("elevenlabs", "", "", ""))
        self.assertEqual(cfg["api_key"], "sk-keepme")

    def test_unknown_preset_is_blank(self):
        tts.update_tts_config({"provider": "piper", "preset": "nope"})
        self.assertEqual(tts.get_tts_config()["preset"], "")
        tts.update_tts_config({"preset": "openai_tts1"})
        self.assertEqual(tts.get_tts_config()["preset"], "", "a preset of another provider is not accepted")
        self.assertEqual(tts.resolve_tts_config()["voice"], "en_US-lessac-medium")

    def test_preset_is_validated_against_the_env_provider(self):
        os.environ["AI_RPG_TTS_PROVIDER"] = "openai"
        tts.update_tts_config({"provider": "off"})
        # The form shows provider openai and omits it from the POST because it did not change.
        tts.update_tts_config({"preset": "openai_tts1", "voice": "fable", "model": "", "base_url": "", "chunk_chars": 0})
        cfg = tts.get_tts_config()
        self.assertEqual(cfg["provider"], "openai")
        self.assertEqual(cfg["preset"], "openai_tts1")
        self.assertEqual(cfg["voice"], "fable")
        self.assertEqual(tts.resolve_tts_config()["model"], "tts-1")
        # A plain speed change is not a provider switch: nothing is reset.
        tts.update_tts_config({"speed": 1.2})
        cfg = tts.get_tts_config()
        self.assertEqual((cfg["preset"], cfg["voice"], cfg["speed"]), ("openai_tts1", "fable", 1.2))

    def test_unknown_stored_keys_are_dropped(self):
        with connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (tts.TTS_CONFIG_KEY, json.dumps({"provider": "piper", "junk": 1, "enabled": "true"})),
            )
        cfg = tts.get_tts_config()
        self.assertNotIn("junk", cfg)
        self.assertTrue(cfg["enabled"])


# --- 4. catalog -------------------------------------------------------------


class TestCatalog(TtsCase):
    COMMON = ("id", "label", "provider", "voice", "model", "base_url", "sample_rate", "speed", "speed_range",
              "chunk_chars", "audio_format", "voices")

    def test_shape(self):
        catalog = tts.tts_catalog()
        self.assertEqual([p["id"] for p in catalog["providers"]], list(tts.PROVIDERS))
        for provider, presets in catalog["presets"].items():
            self.assertTrue(presets)
            for preset in presets:
                for field in self.COMMON:
                    self.assertIn(field, preset, f"{provider}:{preset.get('id')} lacks {field}")
                self.assertEqual(preset["provider"], provider)
            self.assertIn(catalog["default_preset"][provider], [p["id"] for p in presets])
        for preset in catalog["presets"]["piper"]:
            names = [f["name"] for f in preset["files"]]
            self.assertEqual(names, [f"{preset['id']}.onnx", f"{preset['id']}.onnx.json"])
            for entry in preset["files"]:
                self.assertTrue(entry["url"].startswith(tts.PIPER_VOICE_BASE), entry["url"])
                self.assertTrue(entry["url"].endswith("?download=true"))
            self.assertTrue(preset["model_card"].startswith(tts.PIPER_CARD_BASE))
            self.assertEqual(preset["audio_format"], "wav")
            self.assertEqual(preset["chunk_chars"], 600)
        openai_ids = {p["id"] for p in catalog["presets"]["openai"]}
        self.assertEqual(openai_ids, {"openai_gpt4o_mini_tts", "openai_tts1", "openai_compatible"})
        voices = [v["id"] for v in catalog["presets"]["openai"][0]["voices"]]
        self.assertEqual(voices, list(tts._OPENAI_VOICES))
        eleven = catalog["presets"]["elevenlabs"][0]
        self.assertEqual(eleven["output_format"], "mp3_44100_128")
        self.assertEqual(eleven["speed_range"], [0.7, 1.2])
        self.assertEqual([v["label"] for v in eleven["voices"]], ["Rachel", "Adam", "Bella", "Antoni", "George"])

    def test_route_matches_module(self):
        response = self.client.get("/api/tts-catalog")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), tts.tts_catalog())

    def test_catalog_is_a_fresh_copy(self):
        tts.tts_catalog()["presets"]["piper"].clear()
        self.assertEqual(len(tts.tts_catalog()["presets"]["piper"]), 6)


# --- 5. speak refusals ------------------------------------------------------


class TestSpeakRefusals(TtsCase):
    def test_provider_off(self):
        response = self.client.post("/api/tts/speak", json={"text": "Hello there."})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], tts.MSG_OFF)

    def test_enabled_but_provider_off_is_still_off(self):
        tts.update_tts_config({"enabled": True})
        response = self.client.post("/api/tts/speak", json={"text": "Hello there."})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], tts.MSG_OFF)

    def test_empty_after_cleaning(self):
        tts.update_tts_config({"provider": "piper", "enabled": True})
        response = self.client.post("/api/tts/speak", json={"text": "[[L1]]"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], tts.MSG_EMPTY)

    def test_gate_busy_answers_409(self):
        tts.update_tts_config({"provider": "piper", "enabled": True})
        with gpu_gate.gpu_session("llm"):
            response = self.client.post("/api/tts/speak", json={"text": "Hello there."})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], tts.MSG_BUSY)
        self.assertNotIn("tts", gpu_gate._active)

    def test_too_long_is_422(self):
        tts.update_tts_config({"provider": "piper", "enabled": True})
        response = self.client.post("/api/tts/speak", json={"text": "a" * 4001})
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/tts/speak", json={"text": ""})
        self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/tts/speak", json={"text": "hi", "speed": 3})
        self.assertEqual(response.status_code, 422)

    def test_cloud_without_key_on_public_host(self):
        tts.update_tts_config({"provider": "openai", "enabled": True})
        with mock.patch.object(tts, "_http", side_effect=AssertionError("must not be called")):
            response = self.client.post("/api/tts/speak", json={"text": "Hello there."})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], tts.MSG_NO_KEY + " or OPENAI_API_KEY.")
        tts.update_tts_config({"provider": "elevenlabs", "enabled": True})
        response = self.client.post("/api/tts/speak", json={"text": "Hello there."})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], tts.MSG_NO_KEY + " or ELEVENLABS_API_KEY.")


# --- 6. provider shaping ----------------------------------------------------


class TestProviders(TtsCase):
    def _capture(self, payload: bytes = b"ID3fake"):
        calls: list[tuple[str, dict[str, str], dict, float]] = []

        def fake_http(req, timeout):
            headers = {k.lower(): v for k, v in req.headers.items()}
            body = json.loads(req.data.decode("utf-8")) if req.data else {}
            calls.append((req.full_url, headers, body, timeout))
            return payload, {}

        return calls, mock.patch.object(tts, "_http", side_effect=fake_http)

    def test_openai_request(self):
        tts.update_tts_config({"provider": "openai", "enabled": True, "api_key": "k", "speed": 1.3})
        calls, patch = self._capture()
        with patch:
            response = self.client.post("/api/tts/speak", json={"text": "Hello <b>there</b>. [[L1]]"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        self.assertEqual(response.headers["x-morkyn-tts-provider"], "openai")
        self.assertEqual(response.headers["x-morkyn-tts-speed-applied"], "1.30")
        self.assertEqual(response.headers["x-morkyn-tts-chars"], str(len("Hello there.")))
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.content, b"ID3fake")
        self.assertEqual(len(calls), 1)
        url, headers, body, timeout = calls[0]
        self.assertEqual(url, "https://api.openai.com/v1/audio/speech")
        self.assertEqual(headers["authorization"], "Bearer k")
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(body, {"model": "gpt-4o-mini-tts", "input": "Hello there.", "voice": "coral",
                                "speed": 1.3, "response_format": "mp3"})
        self.assertEqual(timeout, 60.0)

    def test_openai_request_overrides(self):
        tts.update_tts_config({"provider": "openai", "enabled": True, "api_key": "k"})
        calls, patch = self._capture()
        with patch:
            response = self.client.post("/api/tts/speak", json={"text": "Hello.", "voice": "onyx", "speed": 0.8})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls[0][2]["voice"], "onyx")
        self.assertEqual(calls[0][2]["speed"], 0.8)
        self.assertEqual(response.headers["x-morkyn-tts-speed-applied"], "0.80")

    def test_openai_compatible_local_server(self):
        tts.update_tts_config({"provider": "openai", "enabled": True, "preset": "openai_compatible",
                               "base_url": "http://127.0.0.1:8880/v1/", "voice": "af_heart"})
        calls, patch = self._capture(b"AB")
        paragraph = ("A sentence of narration goes here. " * 45).strip()  # ~1500 chars
        self.assertGreater(len(paragraph), 1000)
        with patch:
            response = self.client.post("/api/tts/speak", json={"text": paragraph})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(calls), 2, "a 1000-char chunk limit splits a 1500-char paragraph in two")
        self.assertEqual(response.content, b"ABAB")
        for url, headers, body, _ in calls:
            self.assertEqual(url, "http://127.0.0.1:8880/v1/audio/speech")
            self.assertNotIn("authorization", headers)
            self.assertLessEqual(len(body["input"]), 1000)
            self.assertEqual(body["voice"], "af_heart")
            self.assertEqual(body["model"], "tts-1")
        self.assertEqual(" ".join(c[2]["input"] for c in calls), paragraph)

    def test_elevenlabs_request(self):
        tts.update_tts_config({"provider": "elevenlabs", "enabled": True, "api_key": "xi-k", "speed": 1.6})
        calls, patch = self._capture()
        with patch:
            response = self.client.post("/api/tts/speak", json={"text": "Hello there."})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "audio/mpeg")
        self.assertEqual(response.headers["x-morkyn-tts-provider"], "elevenlabs")
        self.assertEqual(response.headers["x-morkyn-tts-speed-applied"], "1.20")
        url, headers, body, _ = calls[0]
        self.assertEqual(url, "https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM?output_format=mp3_44100_128")
        self.assertEqual(headers["xi-api-key"], "xi-k")
        self.assertEqual(headers["accept"], "audio/mpeg")
        self.assertEqual(body["text"], "Hello there.")
        self.assertEqual(body["model_id"], "eleven_multilingual_v2")
        self.assertEqual(body["voice_settings"]["speed"], 1.2)
        self.assertEqual(body["voice_settings"]["stability"], 0.5)

    def test_elevenlabs_key_from_env_and_voice_override(self):
        os.environ["ELEVENLABS_API_KEY"] = "env-key"
        tts.update_tts_config({"provider": "elevenlabs", "enabled": True, "preset": "elevenlabs_flash_v2_5"})
        calls, patch = self._capture()
        with patch:
            response = self.client.post("/api/tts/speak", json={"text": "Hi.", "voice": "custom id/with slash"})
        self.assertEqual(response.status_code, 200, response.text)
        url, headers, body, _ = calls[0]
        self.assertEqual(headers["xi-api-key"], "env-key")
        self.assertIn("/v1/text-to-speech/custom%20id%2Fwith%20slash?", url)
        self.assertEqual(body["model_id"], "eleven_flash_v2_5")

    def test_http_error_becomes_503(self):
        tts.update_tts_config({"provider": "openai", "enabled": True, "api_key": "k"})

        def fake_urlopen(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error": "bad key"}\n'))

        with mock.patch.object(tts.urllib.request, "urlopen", side_effect=fake_urlopen):
            response = self.client.post("/api/tts/speak", json={"text": "Hello."})
        self.assertEqual(response.status_code, 503)
        detail = response.json()["detail"]
        self.assertTrue(detail.startswith("The speech service refused the request (HTTP 401): "), detail)
        self.assertIn("bad key", detail)

    def test_network_error_becomes_503(self):
        tts.update_tts_config({"provider": "openai", "enabled": True, "api_key": "k"})
        with mock.patch.object(tts.urllib.request, "urlopen", side_effect=urllib.error.URLError("no route")):
            response = self.client.post("/api/tts/speak", json={"text": "Hello."})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "The speech service did not answer: no route")
        with mock.patch.object(tts.urllib.request, "urlopen", side_effect=TimeoutError("timed out")):
            response = self.client.post("/api/tts/speak", json={"text": "Hello."})
        self.assertEqual(response.status_code, 503)
        self.assertIn("did not answer", response.json()["detail"])


# --- 7. piper path ----------------------------------------------------------


class TestPiper(TtsCase):
    CODE = "en_US-lessac-medium"

    def test_speak_wav(self):
        tts.update_tts_config({"provider": "piper", "enabled": True, "speed": 1.25})
        _write_fake_voice(self.CODE)
        calls: dict = {}
        sys.modules["piper"] = _fake_piper_module(calls)
        response = self.client.post("/api/tts/speak", json={"text": "The door creaked open. Nobody was there."})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        self.assertEqual(response.headers["x-morkyn-tts-provider"], "piper")
        self.assertEqual(response.headers["x-morkyn-tts-speed-applied"], "1.25")
        with wave.open(io.BytesIO(response.content), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getframerate(), 22050)
            self.assertGreater(wf.getnframes(), 0)
        self.assertAlmostEqual(calls["length_scale"], 1 / 1.25)
        onnx, meta = tts.piper_voice_paths(self.CODE)
        self.assertEqual(calls["load"], (str(onnx), str(meta)))
        self.assertEqual(calls["texts"], ["The door creaked open. Nobody was there."])
        # The loaded voice is cached: a second request does not load again.
        calls.pop("load")
        response = self.client.post("/api/tts/speak", json={"text": "Again."})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("load", calls)
        self.assertNotIn("tts", gpu_gate._active)

    def test_long_paragraph_is_chunked_for_piper(self):
        tts.update_tts_config({"provider": "piper", "enabled": True})
        _write_fake_voice(self.CODE)
        calls: dict = {}
        sys.modules["piper"] = _fake_piper_module(calls)
        text = ("A short sentence of story. " * 60).strip()
        response = self.client.post("/api/tts/speak", json={"text": text})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreater(len(calls["texts"]), 1)
        self.assertTrue(all(len(t) <= 600 for t in calls["texts"]))

    def test_missing_voice_files(self):
        tts.update_tts_config({"provider": "piper", "enabled": True})
        sys.modules["piper"] = _fake_piper_module({})
        response = self.client.post("/api/tts/speak", json={"text": "Hello."})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"],
                         f"The voice {self.CODE} is not downloaded yet. Open Speech settings and press Install.")

    def test_unknown_voice(self):
        tts.update_tts_config({"provider": "piper", "enabled": True})
        sys.modules["piper"] = _fake_piper_module({})
        response = self.client.post("/api/tts/speak", json={"text": "Hello.", "voice": "../../etc/passwd"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], 'Unknown voice "../../etc/passwd". Pick one from the list in Speech settings.')

    def test_engine_not_installed(self):
        tts.update_tts_config({"provider": "piper", "enabled": True})
        _write_fake_voice(self.CODE)
        sys.modules["piper"] = None
        response = self.client.post("/api/tts/speak", json={"text": "Hello."})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], tts.MSG_ENGINE_MISSING)
        self.assertEqual(tts.piper_installed(), (False, ""))

    def test_engine_failure_is_503(self):
        tts.update_tts_config({"provider": "piper", "enabled": True})
        _write_fake_voice(self.CODE)
        module = _fake_piper_module({})

        def boom(*args, **kwargs):
            raise ValueError("onnx says no")

        module.PiperVoice.load = staticmethod(boom)
        sys.modules["piper"] = module
        response = self.client.post("/api/tts/speak", json={"text": "Hello."})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "The local speech engine failed: onnx says no The voice files were removed; "
            "open Speech settings and press Install to download them again.",
        )
        self.assertNotIn("tts", gpu_gate._active)
        # A catalog voice that does not load is a broken download: gone, so Install fetches it again.
        self.assertFalse(tts.piper_voice_present(self.CODE))
        self.assertFalse(any(tts.voice_dir().glob(f"{self.CODE}*")))

    def test_second_speak_waits_for_the_first_instead_of_409(self):
        """Stop-then-Play while the server still synthesizes the abandoned paragraph."""
        tts.update_tts_config({"provider": "piper", "enabled": True})
        _write_fake_voice(self.CODE)
        sys.modules["piper"] = _fake_piper_module({})
        release = threading.Event()
        holding = threading.Event()

        def hold_gate():
            with gpu_gate.gpu_session("tts"):
                holding.set()
                release.wait(5)

        worker = threading.Thread(target=hold_gate, daemon=True)
        worker.start()
        self.assertTrue(holding.wait(5))
        threading.Timer(0.3, release.set).start()
        response = self.client.post("/api/tts/speak", json={"text": "Hello again."})
        worker.join(5)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        self.assertNotIn("tts", gpu_gate._active)


# --- 8. install paths -------------------------------------------------------


class TestInstall(TtsCase):
    CODE = "en_US-lessac-medium"

    def test_refusals(self):
        tts.update_tts_config({"provider": "openai"})
        response = self.client.post("/api/tts/install", json={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], tts.MSG_INSTALL_PROVIDER)
        tts.update_tts_config({"provider": "piper"})
        response = self.client.post("/api/tts/install", json={"what": "nope"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], tts.MSG_INSTALL_STEP)
        response = self.client.post("/api/tts/install", json={"voice": "xx_XX-nope-medium"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], 'Unknown voice "xx_XX-nope-medium". Pick one from the list in Speech settings.')

    def test_pip_failure_is_503(self):
        tts.update_tts_config({"provider": "piper"})
        sys.modules["piper"] = None
        seen: dict = {}

        def fake_run(argv, **kwargs):
            seen["argv"] = argv
            seen["kwargs"] = kwargs
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="boom: no wheel")

        with mock.patch.object(tts.subprocess, "run", side_effect=fake_run):
            response = self.client.post("/api/tts/install", json={"what": "engine"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Could not install the speech engine: boom: no wheel")
        self.assertEqual(seen["argv"][:5], [sys.executable, "-m", "pip", "install", "piper-tts==1.8.0"])
        self.assertNotIn("shell", seen["kwargs"])
        self.assertEqual(seen["kwargs"]["env"]["PIP_NO_INPUT"], "1")

    def test_download_failure_leaves_no_partial(self):
        tts.update_tts_config({"provider": "piper"})
        sys.modules["piper"] = _fake_piper_module({})
        with mock.patch.object(tts.urllib.request, "urlopen", side_effect=urllib.error.URLError("proxy 403")):
            response = self.client.post("/api/tts/install", json={"what": "voice"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], f"Could not download the voice {self.CODE}: proxy 403")
        leftovers = list(tts.voice_dir().glob("*")) if tts.voice_dir().exists() else []
        self.assertEqual(leftovers, [])

    def test_download_success_then_already(self):
        tts.update_tts_config({"provider": "piper"})
        sys.modules["piper"] = _fake_piper_module({})
        fetched: list[str] = []

        def fake_urlopen(req, timeout=0):
            fetched.append(req.full_url)
            if req.full_url.endswith(".onnx.json?download=true"):
                return _FakeResponse(json.dumps({"audio": {"sample_rate": 22050}}).encode())
            return _FakeResponse(b"\0" * (tts.PIPER_MIN_ONNX_BYTES + 1024))

        with mock.patch.object(tts.urllib.request, "urlopen", side_effect=fake_urlopen):
            response = self.client.post("/api/tts/install", json={"what": "all"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["ok"])
        steps = {s["step"]: s for s in body["steps"]}
        self.assertEqual(steps["engine"]["status"], "already", "the fake module counts as installed")
        self.assertEqual(steps["voice"]["status"], "installed")
        self.assertTrue(steps["voice"]["path"].endswith(f"{self.CODE}.onnx"))
        self.assertGreater(steps["voice"]["bytes"], tts.PIPER_MIN_ONNX_BYTES)
        self.assertIn(self.CODE, steps["voice"]["detail"])
        self.assertEqual(len(fetched), 2)
        self.assertTrue(all(u.startswith(tts.PIPER_VOICE_BASE) for u in fetched))
        self.assertTrue(tts.piper_voice_present(self.CODE))
        self.assertTrue(body["status"]["voice_downloaded"])
        self.assertTrue(body["status"]["engine_installed"])
        self.assertTrue(body["status"]["reachable"])
        with mock.patch.object(tts.urllib.request, "urlopen", side_effect=AssertionError("no second download")):
            response = self.client.post("/api/tts/install", json={"what": "all"})
        self.assertEqual(response.status_code, 200)
        steps = {s["step"]: s for s in response.json()["steps"]}
        self.assertEqual(steps["voice"]["status"], "already")
        self.assertEqual(steps["engine"]["status"], "already")

    def test_truncated_download_is_rejected(self):
        tts.update_tts_config({"provider": "piper"})
        sys.modules["piper"] = _fake_piper_module({})
        advertised = 63 * 1024 * 1024

        def fake_urlopen(req, timeout=0):
            if req.full_url.endswith(".onnx.json?download=true"):
                return _FakeResponse(json.dumps({"audio": {"sample_rate": 22050}}).encode())
            response = _FakeResponse(b"\0" * (2 * 1024 * 1024))
            response.headers = {"Content-Length": str(advertised)}
            return response

        with mock.patch.object(tts.urllib.request, "urlopen", side_effect=fake_urlopen):
            response = self.client.post("/api/tts/install", json={"what": "voice"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            f"Could not download the voice {self.CODE}: the download stopped at 2.0 MB of 63.0 MB",
        )
        self.assertFalse(tts.piper_voice_present(self.CODE))
        self.assertFalse(any(tts.voice_dir().glob("*.partial")))
        self.assertFalse(any(tts.voice_dir().glob("*.onnx")))

    def test_install_runs_one_at_a_time(self):
        tts.update_tts_config({"provider": "piper"})
        self.assertTrue(tts._install_lock.acquire(blocking=False))
        try:
            with mock.patch.object(tts.urllib.request, "urlopen", side_effect=AssertionError("must not download")):
                response = self.client.post("/api/tts/install", json={"what": "voice"})
        finally:
            tts._install_lock.release()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], tts.MSG_INSTALL_BUSY)

    def test_bad_voice_json_is_rejected_and_removed(self):
        tts.update_tts_config({"provider": "piper"})
        sys.modules["piper"] = _fake_piper_module({})

        def fake_urlopen(req, timeout=0):
            if req.full_url.endswith(".onnx.json?download=true"):
                return _FakeResponse(b"<html>not a voice</html>")
            return _FakeResponse(b"\0" * (tts.PIPER_MIN_ONNX_BYTES + 1024))

        with mock.patch.object(tts.urllib.request, "urlopen", side_effect=fake_urlopen):
            response = self.client.post("/api/tts/install", json={"what": "voice"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], f"Could not download the voice {self.CODE}: file is not a Piper voice")
        self.assertFalse(any(tts.voice_dir().glob("*")))

    def test_engine_step_skipped_for_voice_only(self):
        tts.update_tts_config({"provider": "piper"})
        _write_fake_voice(self.CODE)
        sys.modules["piper"] = _fake_piper_module({})
        response = self.client.post("/api/tts/install", json={"what": "voice"})
        self.assertEqual(response.status_code, 200)
        steps = {s["step"]: s for s in response.json()["steps"]}
        self.assertEqual(steps["engine"]["status"], "skipped")
        self.assertEqual(steps["voice"]["status"], "already")


# --- 9. status probe --------------------------------------------------------


class TestProbe(TtsCase):
    CODE = "en_US-lessac-medium"

    def test_off(self):
        response = self.client.post("/api/tts-status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertFalse(body["active"])
        self.assertEqual(body["provider"], "off")
        self.assertIn("gate", body)
        self.assertTrue(body["detail"])

    def test_piper_ready(self):
        tts.update_tts_config({"provider": "piper", "enabled": True})
        _write_fake_voice(self.CODE)
        sys.modules["piper"] = _fake_piper_module({})
        body = self.client.post("/api/tts-status").json()
        self.assertTrue(body["ok"], body)
        self.assertTrue(body["engine_installed"])
        self.assertTrue(body["voice_downloaded"])
        self.assertTrue(body["reachable"])
        self.assertTrue(body["active"])
        self.assertIsNone(body["key_set"])
        self.assertTrue(body["voice_path"].endswith(f"{self.CODE}.onnx"))
        self.assertIn(self.CODE, body["detail"])

    def test_piper_not_installed_and_not_downloaded(self):
        tts.update_tts_config({"provider": "piper"})
        sys.modules["piper"] = None
        body = self.client.post("/api/tts-status").json()
        self.assertFalse(body["ok"])
        self.assertFalse(body["engine_installed"])
        self.assertFalse(body["voice_downloaded"])
        self.assertEqual(body["detail"], tts.MSG_ENGINE_MISSING)
        sys.modules["piper"] = _fake_piper_module({})
        body = self.client.post("/api/tts-status").json()
        self.assertFalse(body["ok"])
        self.assertTrue(body["engine_installed"])
        self.assertIn("not downloaded yet", body["detail"])

    def test_elevenlabs_refused_key(self):
        tts.update_tts_config({"provider": "elevenlabs", "api_key": "bad"})
        seen: list[str] = []

        def fake_http(req, timeout, **kwargs):
            seen.append(req.full_url)
            self.assertEqual(kwargs.get("limit"), tts.PROBE_READ_LIMIT, "a probe reads only enough for the status")
            self.assertEqual(req.headers["Xi-api-key"], "bad")
            raise tts.TtsUnavailable("The speech service refused the request (HTTP 401): x", http_status=401)

        with mock.patch.object(tts, "_http", side_effect=fake_http):
            body = self.client.post("/api/tts-status").json()
        self.assertFalse(body["ok"])
        self.assertTrue(body["key_set"])
        self.assertFalse(body["reachable"])
        self.assertEqual(body["detail"], "ElevenLabs refused the API key.")
        self.assertEqual(seen, ["https://api.elevenlabs.io/v1/user"])

    def test_openai_probe_ok_and_missing_key(self):
        tts.update_tts_config({"provider": "openai", "api_key": "k"})
        seen: list[tuple[str, str]] = []

        def fake_http(req, timeout, **kwargs):
            seen.append((req.full_url, req.headers.get("Authorization", "")))
            self.assertEqual(timeout, tts.PROBE_TIMEOUT_S)
            return b"{}", {}

        with mock.patch.object(tts, "_http", side_effect=fake_http):
            body = self.client.post("/api/tts-status").json()
        self.assertTrue(body["ok"], body)
        self.assertTrue(body["reachable"])
        self.assertEqual(seen, [("https://api.openai.com/v1/models", "Bearer k")])
        self.assertIn("Read narration aloud", body["detail"], "not enabled yet: the detail says so")
        with connect() as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (tts.TTS_CONFIG_KEY,))
        tts.update_tts_config({"provider": "openai"})
        with mock.patch.object(tts, "_http", side_effect=AssertionError("no request without a key")):
            body = self.client.post("/api/tts-status").json()
        self.assertFalse(body["ok"])
        self.assertFalse(body["key_set"])
        self.assertEqual(body["detail"], tts.MSG_NO_KEY + " or OPENAI_API_KEY.")


# --- 10. config route -------------------------------------------------------


class TestConfigRoute(TtsCase):
    def test_round_trip(self):
        response = self.client.post("/api/tts-config", json={"provider": "piper", "enabled": True})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["provider"], "piper")
        self.assertTrue(body["enabled"])
        self.assertTrue(body["active"])
        self.assertEqual(body["resolved"]["voice"], "en_US-lessac-medium")
        self.assertEqual(body["resolved"]["chunk_chars"], 600)
        got = self.client.get("/api/tts-config").json()
        self.assertEqual(got["provider"], "piper")
        self.assertTrue(got["active"])
        self.assertEqual(got["api_key"], "")

    def test_partial_post_keeps_other_keys(self):
        self.client.post("/api/tts-config", json={"provider": "openai", "api_key": "sk-1234", "voice": "fable"})
        response = self.client.post("/api/tts-config", json={"speed": 1.5})
        body = response.json()
        self.assertEqual(body["voice"], "fable")
        self.assertEqual(body["speed"], 1.5)
        self.assertTrue(body["api_key_set"])
        self.assertEqual(body["api_key_hint"], "••••1234")
        response = self.client.post("/api/tts-config", json={"api_key": ""})
        self.assertTrue(response.json()["api_key_set"], "blank key on POST keeps the stored one")

    def test_validation(self):
        self.assertEqual(self.client.post("/api/tts-config", json={"speed": 9}).status_code, 422)
        self.assertEqual(self.client.post("/api/tts-config", json={"chunk_chars": 9000}).status_code, 422)
        self.assertEqual(self.client.post("/api/tts-config", json={"voice": "v" * 121}).status_code, 422)
        response = self.client.post("/api/tts-config", json={"provider": "bogus"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "off")

    def test_tts_config_is_not_a_snapshot_key(self):
        import app.world as world

        self.assertNotIn(tts.TTS_CONFIG_KEY, world.SNAPSHOT_SETTING_KEYS)


# --- 11. the key never leaves the machine -----------------------------------


class TestSecretsStayHome(TtsCase):
    def test_state_and_export_do_not_carry_the_key(self):
        tts.update_tts_config({"provider": "openai", "api_key": "sk-secret-ABCD1234", "voice": "fable"})
        state = self.client.get("/api/state")
        self.assertEqual(state.status_code, 200)
        self.assertNotIn("sk-secret", state.text)
        self.assertEqual(state.json()["settings"]["tts_config"]["api_key"], "")
        # Blanked inside get_state() itself: turns, slot loads and the agent API all embed it.
        self.assertEqual(get_state()["settings"]["tts_config"]["api_key"], "")
        self.assertNotIn("sk-secret", json.dumps({"state": get_state()}))
        os.environ.pop("AI_RPG_AGENT_TOKEN", None)
        agent = self.client.get("/api/agent/state")
        self.assertEqual(agent.status_code, 200)
        self.assertNotIn("sk-secret", agent.text)
        self.assertEqual(agent.json()["settings"]["tts_config"]["api_key"], "")
        export = self.client.get("/api/export")
        self.assertEqual(export.status_code, 200)
        self.assertNotIn("sk-secret", export.text)
        rows = [row for row in export.json()["tables"]["settings"] if row["key"] == tts.TTS_CONFIG_KEY]
        self.assertEqual(len(rows), 1, "the row itself still rides along in the export")
        self.assertEqual(json.loads(rows[0]["value"])["api_key"], "")
        # The key is still stored and still used; only the copies that leave are blanked.
        self.assertEqual(tts.resolve_tts_api_key(), "sk-secret-ABCD1234")
        self.assertTrue(self.client.get("/api/tts-config").json()["api_key_set"])

    def test_scrub_helpers_tolerate_odd_shapes(self):
        self.assertIsNone(tts.scrub_tts_state(None))
        self.assertEqual(tts.scrub_tts_state({"settings": []}), {"settings": []})
        odd = {"tables": {"settings": [{"key": "tts_config", "value": "not json"}, "junk"]}}
        self.assertEqual(tts.scrub_tts_export(odd), {"tables": {"settings": [{"key": "tts_config", "value": "not json"}, "junk"]}})
        self.assertEqual(tts.scrub_tts_export({"tables": None}), {"tables": None})


if __name__ == "__main__":
    unittest.main()
