"""LLM-driven matching runner for unmatched event groups.

Reads pipeline/agent-input.json (produced by build.py), sends batches to the
Claude CLI via an injectable invoker, validates responses, and appends results
to pipeline/mappings.agent.yaml.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .agent_prompt import build_prompt
from .agent_response import parse_response, ResponseError
from .claude_invoke import ClaudeInvoker, invoke_claude_cli
from .mappings import MappingEntry, load_mapping, save_mapping
from .ollama_invoke import invoke_ollama, DEFAULT_OLLAMA_MODEL, DEFAULT_OLLAMA_URL
from .openai_compat_invoke import (
    invoke_openai, DEFAULT_OPENAI_MODEL, DEFAULT_OPENAI_BASE_URL,
)


@dataclass
class RunSummary:
    batches_run: int = 0
    batches_rejected: int = 0
    mappings_added: int = 0
    skipped_already_mapped: int = 0


def _quote(s: str) -> str:
    if "," in s or '"' in s:
        return '"' + s.replace('"', '""') + '"'
    return s


_BGG_HEADER = "id,name,yearpublished,bayesaverage,is_expansion"


def _read_bgg_rows(bgg_path: Path) -> list[tuple[int, int, list[str]]]:
    """Read BGG CSV once and project to the columns the agent needs.

    Returns list of (users_rated, bgg_id, [csv_cells]) suitable for sorting
    and partitioning between the popular slice and the per-batch extras.
    """
    import csv
    rows: list[tuple[int, int, list[str]]] = []
    with open(bgg_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                users = int(row.get("usersrated", "") or "0")
            except ValueError:
                users = 0
            cells = [
                row["id"], _quote(row["name"]),
                row.get("yearpublished", ""),
                row.get("bayesaverage", ""),
                row.get("is_expansion", "0"),
            ]
            rows.append((users, int(row["id"]), cells))
    return rows


def _popular_bgg_csv(rows: list[tuple[int, int, list[str]]], top_n: int) -> tuple[str, set[int]]:
    """Top-N rows by users_rated. Stable across batches in a run, so the
    Claude prompt cache reuses it. Returns (csv_text, set_of_ids_in_csv)."""
    sorted_rows = sorted(rows, key=lambda r: -r[0])[:top_n]
    out = [_BGG_HEADER]
    out.extend(",".join(cells) for _, _, cells in sorted_rows)
    return "\n".join(out), {bgg_id for _, bgg_id, _ in sorted_rows}


def _extras_bgg_csv(
    rows: list[tuple[int, int, list[str]]],
    *,
    force_ids: set[int],
    popular_ids: set[int],
) -> str:
    """Per-batch CSV: only the candidate ids that didn't make the popular cut.

    Empty when every candidate is already in the popular slice — in that case
    the prompt suffix omits the 'additional candidates' block entirely, which
    is fine for caching: only the suffix differs per batch.
    """
    extras = [(uid, cells) for _, uid, cells in rows if uid in force_ids and uid not in popular_ids]
    if not extras:
        return ""
    out = [_BGG_HEADER]
    out.extend(",".join(cells) for _, cells in extras)
    return "\n".join(out)


DEFAULT_BACKEND = "openai"
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5"
# Per-backend model defaults live in their invoker modules.

# Backend-specific defaults for prompt sizing.
#
# Claude: prompt caching makes the popular-5k slice cheap on every call after
#   the first; large batches don't help much.
# Ollama / openai (local MLX/GGUF): each call reprocesses the full prompt
#   with no prefix cache, so prompt size is the dominant cost. Smaller
#   slice + larger batch both directly speed up the run.
DEFAULTS_BY_BACKEND = {
    "claude": {"batch_size": 50,  "popular_top_n": 5000},
    "ollama": {"batch_size": 200, "popular_top_n": 500},
    "openai": {"batch_size": 200, "popular_top_n": 500},
}

# Back-compat shim — older callers may still import this name.
DEFAULT_MODEL = DEFAULT_CLAUDE_MODEL


def _build_default_invoker(
    backend: str,
    model: Optional[str],
    *,
    base_url: Optional[str] = None,
    strict_schema: bool = True,
    max_tokens: int = 16384,
):
    if backend == "claude":
        m = model or DEFAULT_CLAUDE_MODEL
        return lambda p: invoke_claude_cli(p, model=m)
    if backend == "ollama":
        m = model or DEFAULT_OLLAMA_MODEL
        return lambda p: invoke_ollama(p, model=m)
    if backend == "openai":
        m = model or DEFAULT_OPENAI_MODEL
        u = base_url or DEFAULT_OPENAI_BASE_URL
        return lambda p: invoke_openai(
            p, model=m, base_url=u,
            strict_schema=strict_schema, max_tokens=max_tokens,
        )
    raise ValueError(
        f"unknown backend: {backend!r} (expected 'claude', 'ollama', or 'openai')"
    )


def _envelope_metadata(envelope: str) -> dict:
    """Pull cost/usage metadata out of the response envelope.

    Handles two shapes: Ollama's wrapped envelope (we emit a `_meta` key)
    and Claude CLI's native envelope (`total_cost_usd` and `usage.*`).
    Returns {} if anything is missing — verbose output is best-effort.
    """
    try:
        d = json.loads(envelope)
    except Exception:
        return {}
    if isinstance(d.get("_meta"), dict):
        return d["_meta"]
    return {
        "cost": float(d.get("total_cost_usd", 0.0)),
        "input_tokens": int(d.get("usage", {}).get("input_tokens", 0)),
        "cache_read": int(d.get("usage", {}).get("cache_read_input_tokens", 0)),
        "cache_create": int(d.get("usage", {}).get("cache_creation_input_tokens", 0)),
        "output_tokens": int(d.get("usage", {}).get("output_tokens", 0)),
        "duration_ms": int(d.get("duration_ms", 0)),
    }


def run(
    *,
    agent_input_path: Path,
    bgg_path: Path,
    manual_path: Path,
    agent_path: Path,
    invoker: Optional[ClaudeInvoker] = None,
    backend: str = DEFAULT_BACKEND,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    strict_schema: bool = True,
    max_tokens: int = 16384,
    batch_size: Optional[int] = None,
    popular_top_n: Optional[int] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> RunSummary:
    # If the caller didn't supply a custom invoker, build one for the
    # selected backend. Tests pass their own invoker, which is unaffected.
    if invoker is None:
        invoker = _build_default_invoker(
            backend, model, base_url=base_url,
            strict_schema=strict_schema, max_tokens=max_tokens,
        )
    effective_model = model or (
        DEFAULT_OPENAI_MODEL if backend == "openai" else
        DEFAULT_OLLAMA_MODEL if backend == "ollama" else
        DEFAULT_CLAUDE_MODEL
    )
    # Resolve sizing defaults from the backend if caller didn't specify.
    backend_defaults = DEFAULTS_BY_BACKEND.get(backend, DEFAULTS_BY_BACKEND["claude"])
    if batch_size is None:
        batch_size = backend_defaults["batch_size"]
    if popular_top_n is None:
        popular_top_n = backend_defaults["popular_top_n"]

    summary = RunSummary()
    blob = json.loads(agent_input_path.read_text())
    items: list[dict] = blob.get("unmatched", [])

    manual = load_mapping(manual_path) if manual_path.exists() else {}
    agent = load_mapping(agent_path) if agent_path.exists() else {}
    already = set(manual) | set(agent)
    items = [it for it in items if it["key"] not in already]
    summary.skipped_already_mapped = len(blob.get("unmatched", [])) - len(items)

    if limit is not None:
        items = items[:limit]
    if not items:
        if verbose:
            print(f"All {summary.skipped_already_mapped} unmatched events already "
                  f"have mappings — nothing to do.", file=sys.stderr)
        return summary

    n_batches = (len(items) + batch_size - 1) // batch_size
    if verbose:
        print(f"Agent runner: {len(items)} events in {n_batches} batches "
              f"of up to {batch_size} (backend: {backend}, model: {effective_model}, "
              f"skipping {summary.skipped_already_mapped} already-mapped)",
              file=sys.stderr, flush=True)

    # Read BGG once and build the cacheable popular slice once.
    # Per-batch we only build a small "extras" CSV with candidate ids that
    # didn't make the popular cut, so the prompt prefix stays byte-identical
    # across batches and Claude's prompt cache hits.
    bgg_rows = _read_bgg_rows(bgg_path)
    popular_csv, popular_ids = _popular_bgg_csv(bgg_rows, top_n=popular_top_n)

    total_cost = 0.0

    for batch_idx, i in enumerate(range(0, len(items), batch_size)):
        batch = items[i:i + batch_size]
        batch_num = batch_idx + 1
        force_ids: set[int] = set()
        for event in batch:
            for cand in event.get("candidates", []):
                if isinstance(cand.get("bgg_id"), int):
                    force_ids.add(cand["bgg_id"])
        extra_csv = _extras_bgg_csv(bgg_rows, force_ids=force_ids, popular_ids=popular_ids)
        prompt = build_prompt(batch, popular_csv, extra_csv or None)

        if dry_run:
            print(f"--- batch {batch_num}/{n_batches} ({len(batch)} items) ---")
            print(prompt[:2000] + ("\n…" if len(prompt) > 2000 else ""))
            continue

        if verbose:
            print(f"  [{batch_num}/{n_batches}] sending {len(batch)} events "
                  f"(prompt {len(prompt) // 1024}KB) ...",
                  file=sys.stderr, end="", flush=True)
        t_start = time.perf_counter()

        envelope = None
        for attempt in (1, 2):
            try:
                envelope = invoker(prompt)
                matches = parse_response(envelope)
                break
            except ResponseError as e:
                if attempt == 2:
                    if verbose:
                        print(f" REJECTED after retry: {e}", file=sys.stderr, flush=True)
                    else:
                        print(f"batch {batch_num} rejected after retry: {e}",
                              file=sys.stderr)
                    summary.batches_rejected += 1
                    matches = None
                    break
                if verbose:
                    print(f" attempt 1 failed, retrying...", file=sys.stderr, end="", flush=True)
                else:
                    print(f"batch {batch_num} attempt 1 failed ({e}); retrying once",
                          file=sys.stderr)

        elapsed = time.perf_counter() - t_start
        summary.batches_run += 1
        if matches is None:
            continue

        n_id = sum(1 for m in matches if m.bgg_id is not None)
        n_null = sum(1 for m in matches if m.bgg_id is None)

        for m in matches:
            agent[m.key] = MappingEntry(
                bgg_id=m.bgg_id,
                note=f"{m.confidence}: {m.reasoning}" if m.reasoning else None,
            )
            summary.mappings_added += 1

        save_mapping(agent_path, agent)

        if verbose and envelope is not None:
            md = _envelope_metadata(envelope)
            total_cost += md.get("cost", 0.0)
            tokens_str = ""
            if md:
                # Claude reports cache_create / cache_read; Ollama reports
                # input_tokens. Pick whichever fields are present.
                if "cache_create" in md or "cache_read" in md:
                    ci = md.get("cache_create", 0) // 1000
                    cr = md.get("cache_read", 0) // 1000
                    ot = md.get("output_tokens", 0)
                    tokens_str = f", cache_create={ci}k cache_read={cr}k out={ot}"
                else:
                    in_ = md.get("input_tokens", 0) // 1000
                    ot = md.get("output_tokens", 0)
                    tokens_str = f", in={in_}k out={ot}"
            cost = md.get("cost", 0.0) if md else 0.0
            cost_str = f", ${cost:.3f} (run total ${total_cost:.2f})" if cost > 0 else ""
            print(f" {elapsed:.1f}s → {n_id} matched, {n_null} null{tokens_str}{cost_str}",
                  file=sys.stderr, flush=True)

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-input", default="pipeline/agent-input.json")
    parser.add_argument("--bgg", default="boardgames_ranks-*.csv")
    parser.add_argument("--manual", default="pipeline/mappings.yaml")
    parser.add_argument("--agent", default="pipeline/mappings.agent.yaml")
    parser.add_argument("--batch-size", type=int, default=None,
                        help=("events per request. defaults to "
                              f"{DEFAULTS_BY_BACKEND['ollama']['batch_size']} for ollama, "
                              f"{DEFAULTS_BY_BACKEND['claude']['batch_size']} for claude."))
    parser.add_argument("--popular-bgg-size", type=int, default=None,
                        help=("how many of the most-rated BGG entries to include in "
                              "the prompt as a general catalog (in addition to the "
                              "per-batch fuzzy candidates, which are always included). "
                              f"defaults to {DEFAULTS_BY_BACKEND['ollama']['popular_top_n']} "
                              f"for ollama, {DEFAULTS_BY_BACKEND['claude']['popular_top_n']} "
                              "for claude. set to 0 to omit entirely."))
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the number of unmatched items processed in this run")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the prompt(s) without invoking claude")
    parser.add_argument("--backend", choices=("ollama", "openai", "claude"),
                        default=DEFAULT_BACKEND,
                        help=f"matcher backend (default: {DEFAULT_BACKEND})")
    parser.add_argument("--model", default=None,
                        help=("model name for the chosen backend. defaults to "
                              f"{DEFAULT_OLLAMA_MODEL!r} for ollama, "
                              f"{DEFAULT_OPENAI_MODEL!r} for openai, "
                              f"{DEFAULT_CLAUDE_MODEL!r} for claude."))
    parser.add_argument("--base-url", default=None,
                        help=("base URL for --backend openai. defaults to "
                              f"{DEFAULT_OPENAI_BASE_URL} (mlx-lm). use "
                              "http://localhost:1234/v1 for LM Studio, etc."))
    parser.add_argument("--no-strict-schema", action="store_true",
                        help=("for --backend openai: send response_format="
                              "json_object instead of json_schema. use this "
                              "if your server doesn't support json_schema "
                              "(e.g. some older versions of mlx-lm)."))
    parser.add_argument("--max-tokens", type=int, default=16384,
                        help=("max output tokens per request (default 16384). "
                              "raise if you see truncated output, especially "
                              "on reasoning-style models that emit a lot before "
                              "the JSON. only used by --backend openai."))
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print per-batch progress + cost as the run proceeds")
    ns = parser.parse_args(argv)

    import glob
    bgg_matches = sorted(glob.glob(ns.bgg))
    if not bgg_matches:
        print(f"no bgg dump matches {ns.bgg!r}", file=sys.stderr)
        return 1

    summary = run(
        agent_input_path=Path(ns.agent_input),
        bgg_path=Path(bgg_matches[-1]),
        manual_path=Path(ns.manual),
        agent_path=Path(ns.agent),
        backend=ns.backend,
        model=ns.model,
        base_url=ns.base_url,
        strict_schema=not ns.no_strict_schema,
        max_tokens=ns.max_tokens,
        batch_size=ns.batch_size,
        popular_top_n=ns.popular_bgg_size,
        limit=ns.limit,
        dry_run=ns.dry_run,
        verbose=ns.verbose,
    )
    print("Agent runner summary:")
    print(f"  batches_run:           {summary.batches_run}")
    print(f"  batches_rejected:      {summary.batches_rejected}")
    print(f"  mappings_added:        {summary.mappings_added}")
    print(f"  skipped_already_mapped:{summary.skipped_already_mapped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
