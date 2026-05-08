"""Tests for the OpenAI-compatible HTTP invoker. Mocks urlopen — no server needed."""
import io
import json
from unittest.mock import patch

import pytest

from pipeline.openai_compat_invoke import (
    invoke_openai, DEFAULT_OPENAI_BASE_URL, DEFAULT_OPENAI_MODEL,
)


def _fake_response(payload: dict) -> io.BytesIO:
    body = json.dumps(payload).encode("utf-8")
    fake = io.BytesIO(body)
    fake.__enter__ = lambda self: self
    fake.__exit__ = lambda self, *a: None
    return fake


def _ok_payload(content: str, *, prompt_tokens: int = 0, completion_tokens: int = 0):
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "test-model",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def test_wraps_response_in_envelope_shape():
    inner = {"matches": [{"key": "K1", "bgg_id": 100, "confidence": "high", "reasoning": "ok"}]}
    payload = _ok_payload(json.dumps(inner), prompt_tokens=12345, completion_tokens=67)
    with patch("pipeline.openai_compat_invoke.urlopen", return_value=_fake_response(payload)):
        envelope = invoke_openai("ignored")
    parsed = json.loads(envelope)
    assert parsed["result"].startswith('{"matches"')
    assert parsed["_meta"]["input_tokens"] == 12345
    assert parsed["_meta"]["output_tokens"] == 67
    assert parsed["_meta"]["cost"] == 0.0


def test_envelope_parses_through_agent_response():
    """End-to-end: invoke_openai -> parse_response yields AgentMatch list."""
    from pipeline.agent_response import parse_response
    inner = {
        "matches": [
            {"key": "K1", "bgg_id": 100, "confidence": "high", "reasoning": "exact"},
            {"key": "K2", "bgg_id": None, "confidence": "low", "reasoning": "n/a"},
        ]
    }
    payload = _ok_payload(json.dumps(inner))
    with patch("pipeline.openai_compat_invoke.urlopen", return_value=_fake_response(payload)):
        envelope = invoke_openai("ignored")
    matches = parse_response(envelope)
    assert len(matches) == 2
    assert matches[0].bgg_id == 100
    assert matches[1].bgg_id is None


def test_request_body_shape_strict_schema_default():
    """Default mode sends response_format=json_schema with our agent schema."""
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data)
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers)
        return _fake_response(_ok_payload('{"matches": []}'))

    with patch("pipeline.openai_compat_invoke.urlopen", side_effect=fake_urlopen):
        invoke_openai(
            "hello",
            model="custom-model",
            base_url="http://localhost:1234/v1",
            api_key="sk-test",
            max_tokens=4096,
        )
    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["data"]["model"] == "custom-model"
    assert captured["data"]["messages"] == [{"role": "user", "content": "hello"}]
    rf = captured["data"]["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "agent_response"
    assert rf["json_schema"]["strict"] is True
    assert "matches" in rf["json_schema"]["schema"]["properties"]
    assert captured["data"]["temperature"] == 0.0
    assert captured["data"]["max_tokens"] == 4096


def test_request_body_strict_schema_disabled():
    """strict_schema=False falls back to looser json_object (for older servers)."""
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data)
        return _fake_response(_ok_payload('{"matches": []}'))

    with patch("pipeline.openai_compat_invoke.urlopen", side_effect=fake_urlopen):
        invoke_openai("hello", strict_schema=False)
    assert captured["data"]["response_format"] == {"type": "json_object"}


def test_trailing_slash_in_base_url_normalized():
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _fake_response(_ok_payload('{"matches": []}'))

    with patch("pipeline.openai_compat_invoke.urlopen", side_effect=fake_urlopen):
        invoke_openai("hello", base_url="http://localhost:8080/v1/")
    assert captured["url"] == "http://localhost:8080/v1/chat/completions"


def test_url_error_raises_with_helpful_message():
    from urllib.error import URLError
    with patch("pipeline.openai_compat_invoke.urlopen", side_effect=URLError("Connection refused")):
        with pytest.raises(RuntimeError, match=r"could not reach OpenAI-compat server"):
            invoke_openai("ignored")


def test_http_error_includes_body():
    from urllib.error import HTTPError
    err_body = b'{"error": "model not found"}'
    err = HTTPError("http://x/v1/chat/completions", 404, "Not Found", {}, io.BytesIO(err_body))
    with patch("pipeline.openai_compat_invoke.urlopen", side_effect=err):
        with pytest.raises(RuntimeError, match=r"HTTP 404"):
            invoke_openai("ignored")


def test_no_choices_raises():
    payload = {"choices": [], "usage": {}}
    with patch("pipeline.openai_compat_invoke.urlopen", return_value=_fake_response(payload)):
        with pytest.raises(RuntimeError, match=r"no choices"):
            invoke_openai("ignored")


def test_error_field_in_response():
    payload = {"error": "rate limit"}
    with patch("pipeline.openai_compat_invoke.urlopen", return_value=_fake_response(payload)):
        with pytest.raises(RuntimeError, match=r"API error"):
            invoke_openai("ignored")
