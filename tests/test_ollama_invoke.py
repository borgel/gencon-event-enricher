"""Tests for the Ollama HTTP invoker. Mocks urlopen so no service is needed."""
import io
import json
from unittest.mock import patch

import pytest

from pipeline.ollama_invoke import invoke_ollama, DEFAULT_OLLAMA_MODEL


def _fake_response(payload: dict) -> io.BytesIO:
    """Build a urlopen-compatible response object."""
    body = json.dumps(payload).encode("utf-8")
    fake = io.BytesIO(body)
    # urlopen's context manager protocol
    fake.__enter__ = lambda self: self
    fake.__exit__ = lambda self, *args: None
    return fake


def test_wraps_response_in_envelope_shape():
    payload = {
        "response": '{"matches": [{"key": "K1", "bgg_id": 100, "confidence": "high", "reasoning": "ok"}]}',
        "prompt_eval_count": 12345,
        "eval_count": 67,
        "total_duration": 5_000_000_000,    # 5 seconds in ns
    }
    with patch("pipeline.ollama_invoke.urlopen", return_value=_fake_response(payload)):
        envelope = invoke_ollama("ignored prompt")
    parsed = json.loads(envelope)
    assert parsed["result"].startswith('{"matches"')
    assert parsed["_meta"]["input_tokens"] == 12345
    assert parsed["_meta"]["output_tokens"] == 67
    assert parsed["_meta"]["duration_ms"] == 5000
    assert parsed["_meta"]["cost"] == 0.0


def test_envelope_parses_through_agent_response():
    """End-to-end: invoke_ollama -> parse_response should yield AgentMatch list."""
    from pipeline.agent_response import parse_response
    inner = {
        "matches": [
            {"key": "K1", "bgg_id": 100, "confidence": "high", "reasoning": "exact"},
            {"key": "K2", "bgg_id": None, "confidence": "low", "reasoning": "n/a"},
        ]
    }
    payload = {"response": json.dumps(inner), "prompt_eval_count": 1, "eval_count": 1}
    with patch("pipeline.ollama_invoke.urlopen", return_value=_fake_response(payload)):
        envelope = invoke_ollama("ignored prompt")
    matches = parse_response(envelope)
    assert len(matches) == 2
    assert matches[0].key == "K1"
    assert matches[0].bgg_id == 100
    assert matches[1].bgg_id is None


def test_request_body_carries_model_and_options():
    payload = {"response": '{"matches": []}'}
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data)
        return _fake_response(payload)

    with patch("pipeline.ollama_invoke.urlopen", side_effect=fake_urlopen):
        invoke_ollama("hello", model="my-custom-model:7b", num_ctx=32768)
    assert captured["data"]["model"] == "my-custom-model:7b"
    assert captured["data"]["format"] == "json"
    assert captured["data"]["stream"] is False
    assert captured["data"]["options"]["num_ctx"] == 32768
    assert captured["data"]["options"]["temperature"] == 0.0


def test_url_error_raises_with_helpful_message():
    from urllib.error import URLError
    with patch("pipeline.ollama_invoke.urlopen", side_effect=URLError("Connection refused")):
        with pytest.raises(RuntimeError, match=r"could not reach Ollama"):
            invoke_ollama("ignored")


def test_ollama_returned_error_field():
    payload = {"error": "model 'foo' not found"}
    with patch("pipeline.ollama_invoke.urlopen", return_value=_fake_response(payload)):
        with pytest.raises(RuntimeError, match=r"ollama API error"):
            invoke_ollama("ignored", model="foo")
