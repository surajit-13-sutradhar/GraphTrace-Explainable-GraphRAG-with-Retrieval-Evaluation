import pytest

from graphtrace.generation.llm_client import parse_retry_delay


def test_parses_hours_minutes_and_seconds():
    expected = 3 * 3600 + 46 * 60 + 7.802155028
    assert parse_retry_delay("Please retry in 3h46m7.802155028s.") == pytest.approx(expected)


def test_parses_seconds_only():
    assert parse_retry_delay("Please retry in 12s.") == pytest.approx(12)


def test_returns_none_when_there_is_no_hint():
    assert parse_retry_delay("Quota exceeded") is None
    assert parse_retry_delay(None) is None