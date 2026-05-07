"""Run `claude -p` as a subprocess. Kept tiny so it's easy to stub in tests."""
from __future__ import annotations
import subprocess
from typing import Callable

ClaudeInvoker = Callable[[str], str]   # prompt -> stdout (envelope JSON)


def invoke_claude_cli(prompt: str) -> str:
    """Default invoker: shells out to `claude -p`. ANTHROPIC_API_KEY must be in env."""
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout
