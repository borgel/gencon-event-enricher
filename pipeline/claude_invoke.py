"""Run `claude -p` as a subprocess. Kept tiny so it's easy to stub in tests."""
from __future__ import annotations
import subprocess
from typing import Callable, Optional

ClaudeInvoker = Callable[[str], str]   # prompt -> stdout (envelope JSON)


def invoke_claude_cli(prompt: str, *, model: Optional[str] = None) -> str:
    """Default invoker: shells out to `claude -p`, piping the prompt over stdin.

    The prompt is passed via stdin rather than as a CLI argument because at
    our scale (full BGG CSV inlined) it exceeds the OS ARG_MAX limit on
    macOS (~256 KB) — argv positionals would raise E2BIG.

    If `model` is given, passes `--model <model>` so the CLI doesn't fall
    back to the user's configured default. Recommended for cost predictability.
    """
    cmd = ["claude", "-p", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    result = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude exited {result.returncode}\n"
            f"--- stderr ---\n{result.stderr}\n"
            f"--- stdout ---\n{result.stdout[:2000]}"
        )
    return result.stdout
