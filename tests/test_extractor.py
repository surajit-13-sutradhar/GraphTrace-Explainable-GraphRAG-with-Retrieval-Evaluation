import json

import pytest

from graphtrace.extraction.extractor import extract_chunk
from graphtrace.extraction.prompts import build_extraction_prompt
from graphtrace.generation.llm_client import LLMEmptyResponseError, LLMRateLimitError
from graphtrace.models import Chunk

CHUNK = Chunk(
    chunk_id="api_gateway#02",
    doc_id="api_gateway",
    doc_title="API Gateway",
    section="Authentication enforcement",
    text="The API Gateway calls the Authentication Service to validate the bearer token.",
)

GOOD_RESPONSE = json.dumps(
    {
        "entities": [
            {"name": "API Gateway", "type": "SERVICE"},
            {"name": "Authentication Service", "type": "SERVICE"},
        ],
        "relationships": [
            {
                "source": "API Gateway",
                "relation": "CALLS",
                "target": "Authentication Service",
                "evidence_quote": "The API Gateway calls the Authentication Service",
            }
        ],
    }
)


class FakeClient:
    model = "fake-model"

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def generate_json(self, *, system_instruction, prompt, schema):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_second_call_is_served_from_cache(tmp_path):
    client = FakeClient(GOOD_RESPONSE)
    first, first_cached = extract_chunk(CHUNK, client, tmp_path)
    second, second_cached = extract_chunk(CHUNK, client, tmp_path)

    assert (first_cached, second_cached) == (False, True)
    assert client.calls == 1
    assert first.relationships == second.relationships
    assert len(first.relationships) == 1


def test_changed_chunk_text_invalidates_cache(tmp_path):
    client = FakeClient(GOOD_RESPONSE)
    extract_chunk(CHUNK, client, tmp_path)
    edited = CHUNK.model_copy(update={"text": CHUNK.text + " It also retries once."})
    _, cached = extract_chunk(edited, client, tmp_path)
    assert cached is False and client.calls == 2


def test_different_model_invalidates_cache(tmp_path):
    client = FakeClient(GOOD_RESPONSE)
    extract_chunk(CHUNK, client, tmp_path)
    client.model = "another-model"
    _, cached = extract_chunk(CHUNK, client, tmp_path)
    assert cached is False and client.calls == 2


def test_corrupted_cache_file_is_treated_as_a_miss(tmp_path):
    client = FakeClient(GOOD_RESPONSE)
    extract_chunk(CHUNK, client, tmp_path)
    (tmp_path / "api_gateway__02.json").write_text("garbage", encoding="utf-8")
    _, cached = extract_chunk(CHUNK, client, tmp_path)
    assert cached is False and client.calls == 2


def test_invalid_json_response_is_not_cached(tmp_path):
    client = FakeClient("{broken")
    result, _ = extract_chunk(CHUNK, client, tmp_path)
    assert result.rejected and "invalid JSON" in result.rejected[0]
    extract_chunk(CHUNK, client, tmp_path)
    assert client.calls == 2  # retried, because nothing was cached


def test_empty_response_becomes_a_rejected_extraction(tmp_path):
    client = FakeClient(LLMEmptyResponseError("blocked"))
    result, cached = extract_chunk(CHUNK, client, tmp_path)
    assert cached is False
    assert result.entities == [] and "empty response" in result.rejected[0]


def test_rate_limit_errors_propagate(tmp_path):
    client = FakeClient(LLMRateLimitError("quota"))
    with pytest.raises(LLMRateLimitError):
        extract_chunk(CHUNK, client, tmp_path)


def test_prompt_wraps_chunk_in_data_delimiters_with_context():
    prompt = build_extraction_prompt(CHUNK)
    assert "<chunk>" in prompt and "</chunk>" in prompt
    assert CHUNK.text in prompt
    assert "Authentication enforcement" in prompt