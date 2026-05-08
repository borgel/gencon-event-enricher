"""Run a local (or any) LLM via an OpenAI-compatible HTTP API.

Works with any server that implements POST /v1/chat/completions:
  - mlx-lm     (default :8080/v1) — headless, MLX-accelerated on Apple Silicon
  - LM Studio  (:1234/v1)         — GUI app, MLX or GGUF
  - vLLM       (:8000/v1)         — production-grade serving
  - llama-server (:8080/v1)       — bundled with llama.cpp
  - OpenAI proper (api.openai.com/v1) — needs an API key

Returns a string envelope shaped like Claude's so parse_response() works
unchanged across all backends.
"""
from __future__ import annotations
import json
import os
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Default to mlx-lm's port because the project policy is "scriptable/headless
# where possible" — mlx-lm runs as a CLI server, LM Studio needs the GUI.
DEFAULT_OPENAI_BASE_URL = os.environ.get(
    "OPENAI_BASE_URL", "http://localhost:8080/v1"
)
DEFAULT_OPENAI_MODEL = os.environ.get(
    "OPENAI_MODEL", "mlx-community/Qwen2.5-14B-Instruct-4bit"
)


def invoke_openai(
    prompt: str,
    *,
    model: str = DEFAULT_OPENAI_MODEL,
    base_url: str = DEFAULT_OPENAI_BASE_URL,
    api_key: Optional[str] = None,
    timeout: float = 1800.0,
    max_tokens: int = 16384,
) -> str:
    """POST to <base_url>/chat/completions, wrap response so parse_response accepts it.

    Returns a JSON string with shape:
        {"result": "<model JSON text>", "_meta": {...token stats...}}

    Local servers usually ignore the API key but reject missing Authorization
    headers, so we send a placeholder. Set OPENAI_API_KEY (or pass api_key=)
    to talk to OpenAI proper.
    """
    api_key = api_key or os.environ.get("OPENAI_API_KEY") or "not-needed"

    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        # Most OpenAI-compat servers honor json_object; LM Studio also supports
        # json_schema for stricter constraints. json_object is the broadest.
        "response_format": {"type": "json_object"},
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

    content = choices[0].get("message", {}).get("content", "")
    usage = data.get("usage", {}) or {}

    return json.dumps({
        "result": content,
        "_meta": {
            "cost": 0.0,   # local; cloud OpenAI users can compute from token counts
            "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "output_tokens": int(usage.get("completion_tokens", 0) or 0),
        },
    })
