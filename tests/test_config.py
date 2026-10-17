import pytest

from graphtrace.config import Settings


def test_missing_api_key_raises_actionable_error():
    settings = Settings(gemini_api_key=None, gemini_model="any-model")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        settings.require_api_key()


def test_present_api_key_is_returned():
    settings = Settings(gemini_api_key="abc", gemini_model="any-model")
    assert settings.require_api_key() == "abc"