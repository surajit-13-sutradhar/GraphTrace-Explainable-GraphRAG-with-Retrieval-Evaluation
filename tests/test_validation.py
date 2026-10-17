import json

from graphtrace.extraction.validation import validate_extraction
from graphtrace.models import Chunk

CHUNK = Chunk(
    chunk_id="api_gateway#02",
    doc_id="api_gateway",
    doc_title="API Gateway",
    section="Authentication enforcement",
    text="For every protected route, the API Gateway calls the Authentication Service "
    "to validate the bearer token.",
)

GOOD_REL = {
    "source": "API Gateway",
    "relation": "CALLS",
    "target": "Authentication Service",
    "evidence_quote": "the API Gateway calls the Authentication Service",
}


def raw(entities=None, relationships=None) -> str:
    return json.dumps({"entities": entities or [], "relationships": relationships or []})


def test_valid_relationship_gets_provenance_and_verified_quote():
    result = validate_extraction(raw(relationships=[GOOD_REL]), CHUNK)
    assert result.rejected == []
    rel = result.relationships[0]
    assert (rel.source, rel.relation.value, rel.target) == (
        "API Gateway", "CALLS", "Authentication Service",
    )
    assert rel.chunk_id == "api_gateway#02"
    assert rel.quote_verified is True


def test_quote_check_ignores_case_and_whitespace():
    rel = {**GOOD_REL, "evidence_quote": "THE API  Gateway\ncalls the authentication service"}
    result = validate_extraction(raw(relationships=[rel]), CHUNK)
    assert result.relationships[0].quote_verified is True


def test_fabricated_quote_is_kept_but_flagged():
    rel = {**GOOD_REL, "evidence_quote": "the gateway depends on a magic oracle"}
    result = validate_extraction(raw(relationships=[rel]), CHUNK)
    assert len(result.relationships) == 1
    assert result.relationships[0].quote_verified is False


def test_invalid_relation_is_rejected_but_valid_items_survive():
    bad = {**GOOD_REL, "relation": "LOVES"}
    result = validate_extraction(raw(relationships=[bad, GOOD_REL]), CHUNK)
    assert len(result.relationships) == 1
    assert len(result.rejected) == 1
    assert "relationship[0]" in result.rejected[0]


def test_self_loop_is_rejected():
    loop = {**GOOD_REL, "target": "api gateway"}
    result = validate_extraction(raw(relationships=[loop]), CHUNK)
    assert result.relationships == []
    assert "self-referential" in result.rejected[0]


def test_llm_supplied_chunk_id_is_overwritten():
    rel = {**GOOD_REL, "chunk_id": "totally_made_up#99"}
    result = validate_extraction(raw(relationships=[rel]), CHUNK)
    assert result.relationships[0].chunk_id == "api_gateway#02"


def test_invalid_entities_are_rejected():
    entities = [
        {"name": "API Gateway", "type": "SERVICE"},
        {"name": "Mystery", "type": "ROBOT"},
        {"name": "   ", "type": "SERVICE"},
    ]
    result = validate_extraction(raw(entities=entities), CHUNK)
    assert [e.name for e in result.entities] == ["API Gateway"]
    assert len(result.rejected) == 2


def test_malformed_json_returns_empty_result_with_reason():
    result = validate_extraction("{not json", CHUNK)
    assert result.entities == [] and result.relationships == []
    assert "invalid JSON" in result.rejected[0]


def test_non_object_json_is_rejected():
    result = validate_extraction("[1, 2, 3]", CHUNK)
    assert "not a JSON object" in result.rejected[0]


def test_non_list_fields_are_rejected():
    result = validate_extraction(json.dumps({"entities": "oops", "relationships": 5}), CHUNK)
    assert len(result.rejected) == 2