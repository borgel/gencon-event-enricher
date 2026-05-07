import json
import pytest
from pipeline.agent_response import parse_response, ResponseError


VALID_INNER = {
    "matches": [
        {"key": "K1", "bgg_id": 100, "confidence": "high", "reasoning": "exact"},
        {"key": "K2", "bgg_id": None, "confidence": "low", "reasoning": "not a game"},
    ]
}
VALID_ENVELOPE = {"type": "result", "result": json.dumps(VALID_INNER)}


def test_parse_valid_response():
    matches = parse_response(json.dumps(VALID_ENVELOPE))
    assert len(matches) == 2
    assert matches[0].key == "K1"
    assert matches[0].bgg_id == 100
    assert matches[1].bgg_id is None


def test_strips_markdown_fences():
    fenced = {"type": "result", "result": "```json\n" + json.dumps(VALID_INNER) + "\n```"}
    matches = parse_response(json.dumps(fenced))
    assert len(matches) == 2


def test_invalid_envelope_raises():
    with pytest.raises(ResponseError):
        parse_response("not json at all")


def test_inner_not_json_raises():
    bad = {"type": "result", "result": "definitely not json"}
    with pytest.raises(ResponseError):
        parse_response(json.dumps(bad))


def test_schema_violation_raises():
    bad = {"type": "result", "result": json.dumps({"matches": [{"key": "K1"}]})}  # missing fields
    with pytest.raises(ResponseError):
        parse_response(json.dumps(bad))


def test_extra_keys_in_match_object_rejected():
    bad_inner = {"matches": [{
        "key": "K1", "bgg_id": 100, "confidence": "high",
        "reasoning": "ok", "extra": "field",
    }]}
    bad = {"type": "result", "result": json.dumps(bad_inner)}
    with pytest.raises(ResponseError):
        parse_response(json.dumps(bad))
