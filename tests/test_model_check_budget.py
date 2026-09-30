import os
import unittest
from contextlib import contextmanager

from app.llm import (
    API_VERIFY_TOKENS,
    LOCAL_VERIFY_TOKENS,
    _configured_response_tokens,
    _json_repair_token_cap,
    _turn_max_tokens,
    _turn_token_default,
    model_check_profile,
)

_BUDGET_ENV = (
    "AI_RPG_JSON_REPAIR_TOKENS",
    "AI_RPG_API_RESPONSE_HARD_CAP_TOKENS",
    "AI_RPG_RESPONSE_HARD_CAP_TOKENS",
    "AI_RPG_MAX_RESPONSE_HARD_CAP_TOKENS",
    "AI_RPG_MAX_RESPONSE_TOKENS",
    "AI_RPG_TURN_VERIFY_TOKENS",
    "AI_RPG_TURN_DRAFT_TOKENS",
)


@contextmanager
def _cleared_budget_env():
    saved = {key: os.environ.pop(key) for key in _BUDGET_ENV if key in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def _caps(**extra):
    config = {
        "response_token_cap": 1500,
        "response_token_hard_cap": 2000,
    }
    config.update(extra)
    return config


def _rich(detail="rich"):
    return {"settings": {"playthrough_options": {"narration_detail": detail}}}


class ModelCheckBudgetTests(unittest.TestCase):
    def test_profile_splits_api_from_a_7b(self):
        self.assertEqual(
            model_check_profile(_caps(provider="openai", api_model="grok-4.7")),
            "api",
        )
        self.assertEqual(
            model_check_profile(_caps(provider="xai", api_model="grok-4.7")),
            "api",
        )
        self.assertEqual(
            model_check_profile(_caps(provider="openai", api_model="gpt-4.1-mini")),
            "api",
        )
        self.assertEqual(
            model_check_profile(_caps(provider="mle", mle_model="qwen2.5:7b-instruct")),
            "local_small",
        )
        self.assertEqual(
            model_check_profile(_caps(provider="mle", mle_model="qwen3:8b")),
            "local_small",
        )
        self.assertEqual(
            model_check_profile(
                _caps(
                    provider="llama_cpp",
                    gguf_model_path=r"D:\models\qwen2.5-7b-instruct-q4_k_m.gguf",
                )
            ),
            "local_small",
        )
        self.assertEqual(
            model_check_profile(_caps(provider="mle", mle_model="phi3")),
            "local_small",
        )
        for name in ("qwen2.5:14b", "qwen2.5:32b", "qwen2.5:70b", "llama3.1"):
            self.assertEqual(
                model_check_profile(_caps(provider="mle", mle_model=name)),
                "local",
                name,
            )

    def test_verify_budget_is_higher_for_an_api_than_a_7b(self):
        api = _caps(provider="openai", api_model="grok-4.7")
        small = _caps(provider="mle", mle_model="qwen2.5:7b-instruct")
        self.assertEqual(_turn_token_default(_rich(), "verify", api), API_VERIFY_TOKENS["rich"])
        self.assertEqual(_turn_token_default(_rich(), "verify", small), LOCAL_VERIFY_TOKENS["rich"])
        self.assertGreater(API_VERIFY_TOKENS["rich"], LOCAL_VERIFY_TOKENS["rich"])
        self.assertEqual(_turn_token_default(_rich(), "draft", api), 1700)
        self.assertEqual(_turn_token_default(_rich(), "draft", small), 1700)
        for detail in ("concise", "balanced", "expansive"):
            self.assertEqual(_turn_token_default(_rich(detail), "verify", api), API_VERIFY_TOKENS[detail])
            self.assertEqual(_turn_token_default(_rich(detail), "verify", small), LOCAL_VERIFY_TOKENS[detail])
            self.assertGreater(API_VERIFY_TOKENS[detail], LOCAL_VERIFY_TOKENS[detail])

    def test_default_hard_cap_does_not_clip_an_api_check(self):
        api = _caps(provider="openai", api_model="grok-4.7")
        small = _caps(provider="mle", mle_model="qwen2.5:7b-instruct")
        with _cleared_budget_env():
            self.assertEqual(_configured_response_tokens(api, 3600), 3600)
            self.assertEqual(_configured_response_tokens(small, 3600), 2000)
            self.assertEqual(_json_repair_token_cap(api, 3600), 3600)
            self.assertLessEqual(_json_repair_token_cap(small, 1300), 2000)

    def test_explicit_hard_cap_still_wins(self):
        api = _caps(provider="openai", api_model="grok-4.7", response_token_hard_cap=2500)
        with _cleared_budget_env():
            self.assertEqual(_configured_response_tokens(api, 3600), 2500)

    def test_env_pin_overrides_the_profile_table(self):
        api = _caps(provider="openai", api_model="grok-4.7")
        with _cleared_budget_env():
            os.environ["AI_RPG_TURN_VERIFY_TOKENS"] = "900"
            self.assertEqual(_turn_max_tokens(_rich(), "verify", config=api), 900)


if __name__ == "__main__":
    unittest.main()
