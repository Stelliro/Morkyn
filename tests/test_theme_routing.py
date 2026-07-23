"""Unit checks for session theme → model adapter routing (no Ollama)."""

from __future__ import annotations

from app.llm import (
    apply_theme_model_routing,
    get_model_config,
    model_config_scope,
    normalize_theme_adapter_map,
    resolve_theme_model_override,
)


def test_normalize_theme_adapter_map_keeps_known_hints():
    m = normalize_theme_adapter_map({"isekai_rpg": " morkyn-isekai ", "bogus": "x"})
    assert m["isekai_rpg"] == "morkyn-isekai"
    assert m["system_rpg"] == ""
    assert m["grimdark"] == ""
    assert m["default"] == ""
    assert m["bogus"] == "x"


def test_resolve_prefers_session_theme_model():
    source, model = resolve_theme_model_override(
        {"adapter_hint": "isekai_rpg", "theme_model": "session-special"},
        {"isekai_rpg": "mapped-isekai"},
    )
    assert source == "session_theme.theme_model"
    assert model == "session-special"


def test_resolve_uses_adapter_map():
    source, model = resolve_theme_model_override(
        {"adapter_hint": "isekai_rpg", "theme_model": ""},
        {"isekai_rpg": "mapped-isekai"},
    )
    assert source == "theme_adapter_map[isekai_rpg]"
    assert model == "mapped-isekai"


def test_resolve_empty_when_unmapped():
    source, model = resolve_theme_model_override(
        {"adapter_hint": "grimdark"},
        {"isekai_rpg": "mapped-isekai"},
    )
    assert source == ""
    assert model == ""


def test_apply_routing_ollama_swaps_model():
    cfg = {
        "provider": "ollama",
        "ollama_model": "qwen3:8b",
        "theme_adapter_map": {"isekai_rpg": "morkyn-isekai-dm"},
    }
    out = apply_theme_model_routing(cfg, {"adapter_hint": "isekai_rpg"})
    assert out["ollama_model"] == "morkyn-isekai-dm"
    assert out["theme_model_active"] == "morkyn-isekai-dm"
    assert "theme_adapter_map" in out
    # Base config object not mutated.
    assert cfg["ollama_model"] == "qwen3:8b"


def test_apply_routing_openai_swaps_api_model():
    cfg = {
        "provider": "openai",
        "api_model": "grok-4.5",
        "theme_adapter_map": {"grimdark": "special-grim"},
    }
    out = apply_theme_model_routing(cfg, {"adapter_hint": "grimdark"})
    assert out["api_model"] == "special-grim"


def test_apply_routing_llama_cpp_path():
    cfg = {
        "provider": "llama_cpp",
        "gguf_model_path": "D:\\models\\base.gguf",
        "theme_adapter_map": {"isekai_rpg": "D:\\models\\isekai.gguf"},
    }
    out = apply_theme_model_routing(cfg, {"adapter_hint": "isekai_rpg"})
    assert out["gguf_model_path"] == "D:\\models\\isekai.gguf"


def test_model_config_scope_overrides_get_model_config():
    base = get_model_config(ignore_override=True)
    themed = {**base, "ollama_model": "theme-only-for-scope", "provider": "ollama"}
    assert get_model_config().get("ollama_model") != "theme-only-for-scope" or base.get("ollama_model") == "theme-only-for-scope"
    with model_config_scope(themed):
        assert get_model_config()["ollama_model"] == "theme-only-for-scope"
    # Cleared after scope.
    after = get_model_config()
    assert after.get("ollama_model") != "theme-only-for-scope" or base.get("ollama_model") == "theme-only-for-scope"
