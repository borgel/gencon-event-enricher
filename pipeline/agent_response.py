"""Parse and validate the Claude CLI's response envelope + inner JSON."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from jsonschema import validate, ValidationError

_SCHEMA_PATH = Path(__file__).parent / "agent_response_schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text())


class ResponseError(Exception):
    """Raised when the agent response is malformed."""


@dataclass
class AgentMatch:
    key: str
    bgg_id: Optional[int]
    confidence: str
    reasoning: str


def _strip_fences(s: str) -> str:
    s = s.strip()
    m = re.match(r"^```(?:json)?\s*\n(.*)\n```\s*$", s, flags=re.DOTALL)
    return m.group(1) if m else s


def parse_response(envelope_text: str) -> list[AgentMatch]:
    try:
        envelope = json.loads(envelope_text)
    except json.JSONDecodeError as e:
        raise ResponseError(f"envelope is not JSON: {e}") from e

    inner_text = envelope.get("result")
    if not isinstance(inner_text, str):
        raise ResponseError(f"envelope.result missing or not a string: {envelope!r}")
    inner_text = _strip_fences(inner_text)

    try:
        inner = json.loads(inner_text)
    except json.JSONDecodeError as e:
        raise ResponseError(f"inner result is not JSON: {e}\n--- raw inner: ---\n{inner_text}") from e

    try:
        validate(inner, _SCHEMA)
    except ValidationError as e:
        raise ResponseError(f"schema violation: {e.message}") from e

    return [
        AgentMatch(
            key=m["key"],
            bgg_id=m["bgg_id"],
            confidence=m["confidence"],
            reasoning=m["reasoning"],
        )
        for m in inner["matches"]
    ]
