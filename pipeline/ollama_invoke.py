"""Run a local model via Ollama's HTTP API.

Ollama exposes /api/generate at http://localhost:11434 by default. We send
our prompt with format="json" so the model is constrained to emit JSON,
and options.num_ctx large enough to fit the BGG list + events.

The function returns a string envelope shaped like Claude's so that the
existing parse_response() in agent_response.py works unchanged.
"""
from __future__ import annotations
import json
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:14b"
# 200 KB prompts come out to ~50–60k tokens; 64k context covers that with
# headroom for the model's reasoning/output.
DEFAULT_NUM_CTX = 65536


def invoke_ollama(
    prompt: str,
    *,
    model: str = DEFAULT_OLLAMA_MODEL,
    base_url: str = DEFAULT_OLLAMA_URL,
    num_ctx: int = DEFAULT_NUM_CTX,
    timeout: float = 600.0,
) -> str:
    """POST to /api/generate, wrap the response so parse_response accepts it.

    Returns a JSON string with shape:
        {"result": "<model JSON text>", "_meta": {...token/duration stats...}}

    Raises RuntimeError on connection failure or non-2xx status.
    """
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "num_ctx": num_ctx,
            "temperature": 0.0,   # deterministic — matching, not creative
        },
    }).encode("utf-8")

    req = Request(
        f"{base_url}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except URLError as e:
        raise RuntimeError(
            f"could not reach Ollama at {base_url}: {e}\n"
            f"  Is `ollama serve` running? Try: curl {base_url}/api/tags"
        ) from e
    except Exception as e:
        raise RuntimeError(f"ollama HTTP call failed: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"ollama returned non-JSON body: {raw[:500]!r}") from e

    if "error" in data:
        raise RuntimeError(f"ollama API error: {data['error']}")

    return json.dumps({
        "result": data.get("response", ""),
        "_meta": {
            "cost": 0.0,
            "input_tokens": int(data.get("prompt_eval_count", 0) or 0),
            "output_tokens": int(data.get("eval_count", 0) or 0),
            # Ollama's durations are nanoseconds; convert to ms.
            "duration_ms": int((data.get("total_duration", 0) or 0) // 1_000_000),
            "load_duration_ms": int((data.get("load_duration", 0) or 0) // 1_000_000),
            "eval_duration_ms": int((data.get("eval_duration", 0) or 0) // 1_000_000),
        },
    })
