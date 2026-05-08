"""Run a local (or any) LLM via an OpenAI-compatible HTTP API.

Works with any server that implements POST /v1/chat/completions:
  - mlx-lm     (default :8080/v1) — headless, MLX-accelerated on Apple Silicon
  - LM Studio  (:1234/v1)         — GUI app, MLX or GGUF
  - vLLM       (:8000/v1)         — production-grade serving
  - llama-server (:8080/v1)       — bundled with llama.cpp
  - OpenAI proper (api.openai.com/v1) — needs an API key

Returns a string envelope shaped like Claude's so parse_response() works
unchanged across all backends.

We send response_format={type:json_schema} with the agent's response schema
embedded — this is required by LM Studio (it rejects json_object) and works
on OpenAI proper. Servers that don't grok json_schema can fall back via
the --no-strict-schema flag (sends type:json_object instead).
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Defaults match the user's working LM Studio setup. Override via the
# OPENAI_BASE_URL / OPENAI_MODEL env vars or --base-url / --model flags
# to point at a different server (mlx-lm on :8080, OpenAI cloud, etc.).
DEFAULT_OPENAI_BASE_URL = os.environ.get(
    "OPENAI_BASE_URL", "http://localhost:1234/v1"
)
DEFAULT_OPENAI_MODEL = os.environ.get(
    "OPENAI_MODEL", "qwen/qwen3.5-9b"
)


_SCHEMA_PATH = Path(__file__).parent / "agent_response_schema.json"
_AGENT_RESPONSE_SCHEMA = json.loads(_SCHEMA_PATH.read_text())


def _response_format(strict: bool) -> dict:
    if strict:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "agent_response",
                "strict": True,
                # Some servers (OpenAI strict mode, LM Studio) require the
                # schema to live under "schema"; pass it directly.
                "schema": _AGENT_RESPONSE_SCHEMA,
            },
        }
    return {"type": "json_object"}


def invoke_openai(
    prompt: str,
    *,
    model: str = DEFAULT_OPENAI_MODEL,
    base_url: str = DEFAULT_OPENAI_BASE_URL,
    api_key: Optional[str] = None,
    timeout: float = 1800.0,
    max_tokens: int = 16384,
    strict_schema: bool = True,
) -> str:
    """POST to <base_url>/chat/completions, wrap response so parse_response accepts it.

    Returns a JSON string with shape:
        {"result": "<model JSON text>", "_meta": {...token stats...}}

    Local servers usually ignore the API key but reject missing Authorization
    headers, so we send a placeholder. Set OPENAI_API_KEY (or pass api_key=)
    to talk to OpenAI proper.

    `strict_schema=True` (default) sends response_format=json_schema with our
    agent_response_schema.json embedded. LM Studio requires this. Set False
    to fall back to json_object for servers that don't support json_schema.
    """
    api_key = api_key or os.environ.get("OPENAI_API_KEY") or "not-needed"

    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": _response_format(strict_schema),
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    url = f"{base_url.rstrip('/')}/chat/completions"
    req = Request(
        url, data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = "<failed to read error body>"
        raise RuntimeError(
            f"server at {base_url} returned HTTP {e.code}:\n{err_body[:1000]}"
        ) from e
    except URLError as e:
        raise RuntimeError(
            f"could not reach OpenAI-compat server at {base_url}: {e}\n"
            f"  - mlx-lm:    `mlx_lm.server --model {DEFAULT_OPENAI_MODEL}` (default :8080)\n"
            f"  - LM Studio: enable the local server in the app (default :1234, set --base-url)\n"
            f"  - check: curl {base_url}/models"
        ) from e
    except Exception as e:
        raise RuntimeError(f"OpenAI-compat call failed: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"server returned non-JSON body: {raw[:500]!r}") from e

    if isinstance(data.get("error"), (str, dict)):
        raise RuntimeError(f"OpenAI-compat API error: {data['error']}")

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"server returned no choices: {data}")

    msg = choices[0].get("message", {}) or {}
    content = (msg.get("content") or "").strip()
    finish_reason = choices[0].get("finish_reason")
    usage = data.get("usage", {}) or {}

    # Reasoning-style models (qwen3, qwen3.5, deepseek-r1, etc.) sometimes
    # route the structured answer into `reasoning_content` (or `reasoning`)
    # and leave `content` empty. Treat those as equivalent for our purposes.
    if not content:
        for fallback_key in ("reasoning_content", "reasoning"):
            fallback = (msg.get(fallback_key) or "").strip()
            if fallback:
                content = fallback
                break

    if not content:
        # Empty even after reasoning fallback — likely the model used all
        # max_tokens before emitting anything we can parse.
        raise RuntimeError(
            f"server returned empty content (and no reasoning_content). "
            f"finish_reason={finish_reason!r}, "
            f"output_tokens={usage.get('completion_tokens', 0)}/{max_tokens}. "
            f"For reasoning models, the budget may have been consumed before "
            f"any JSON was produced. Try a non-reasoning model "
            f"(qwen2.5:14b, llama3.1:8b) or raise max_tokens. "
            f"Full message: {msg!r}"
        )

    return json.dumps({
        "result": content,
        "_meta": {
            "cost": 0.0,   # local; cloud OpenAI users can compute from token counts
            "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "output_tokens": int(usage.get("completion_tokens", 0) or 0),
        },
    })
