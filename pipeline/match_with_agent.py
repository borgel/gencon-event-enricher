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


def _bgg_csv_subset(bgg_path: Path, *, popular_top_n: int, force_ids: set[int]) -> str:
    """Build a slim BGG CSV containing the popular_top_n most-rated games plus
    every BGG id in force_ids (typically the candidate ids from the current batch).

    Why slimmed: the full BGG dump is ~177k entries / ~9 MB, well past Claude's
    1M-token context. We take the most-rated games as the broad "any reasonable
    board game the agent might recognize" set, and unconditionally include the
    candidates we already surfaced via fuzzy matching for the current batch.
    """
    import csv
    rows: list[tuple[int, list[str]]] = []
    with open(bgg_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                users = int(row.get("usersrated", "") or "0")
            except ValueError:
                users = 0
            id_ = int(row["id"])
            rows.append((users, [
                row["id"], _quote(row["name"]),
                row.get("yearpublished", ""),
                row.get("bayesaverage", ""),
                row.get("is_expansion", "0"),
            ]))

    # Top N by users_rated, descending.
    rows.sort(key=lambda r: -r[0])
    popular = rows[:popular_top_n]

    # Force-include any candidate ids that didn't make the popular cut.
    popular_ids = {int(r[1][0]) for r in popular}
    extras = [r for r in rows if int(r[1][0]) in force_ids and int(r[1][0]) not in popular_ids]

    out_lines = ["id,name,yearpublished,bayesaverage,is_expansion"]
    out_lines.extend(",".join(cells) for _, cells in popular + extras)
    return "\n".join(out_lines)


DEFAULT_MODEL = "claude-haiku-4-5"


def _envelope_metadata(envelope: str) -> dict:
    """Pull cost/usage metadata out of the Claude CLI's JSON envelope.
    Returns {} if anything is missing — verbose output is best-effort."""
    try:
        d = json.loads(envelope)
        return {
            "cost": float(d.get("total_cost_usd", 0.0)),
            "input_tokens": int(d.get("usage", {}).get("input_tokens", 0)),
            "cache_read": int(d.get("usage", {}).get("cache_read_input_tokens", 0)),
            "cache_create": int(d.get("usage", {}).get("cache_creation_input_tokens", 0)),
            "output_tokens": int(d.get("usage", {}).get("output_tokens", 0)),
            "duration_ms": int(d.get("duration_ms", 0)),
        }
    except Exception:
        return {}


def run(
    *,
    agent_input_path: Path,
    bgg_path: Path,
    manual_path: Path,
    agent_path: Path,
    invoker: Optional[ClaudeInvoker] = None,
    model: Optional[str] = DEFAULT_MODEL,
    batch_size: int = 50,
    limit: Optional[int] = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> RunSummary:
    # If the caller didn't supply a custom invoker, build one bound to the
    # selected model. Tests pass their own invoker (which ignores model).
    if invoker is None:
        def invoker(prompt: str) -> str:
            return invoke_claude_cli(prompt, model=model)

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
              f"of up to {batch_size} (model: {model or 'default'}, "
              f"skipping {summary.skipped_already_mapped} already-mapped)",
              file=sys.stderr, flush=True)

    total_cost = 0.0

    for batch_idx, i in enumerate(range(0, len(items), batch_size)):
        batch = items[i:i + batch_size]
        batch_num = batch_idx + 1
        # Per-batch BGG slice: top 5k most-rated games + every candidate id
        # referenced by events in this batch. Keeps the prompt under context
        # while still giving the agent a real catalog to verify against.
        force_ids: set[int] = set()
        for event in batch:
            for cand in event.get("candidates", []):
                if isinstance(cand.get("bgg_id"), int):
                    force_ids.add(cand["bgg_id"])
        bgg_csv = _bgg_csv_subset(bgg_path, popular_top_n=5000, force_ids=force_ids)
        prompt = build_prompt(batch, bgg_csv)

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
            cost_str = f", ${md['cost']:.3f} (run total ${total_cost:.2f})" if md else ""
            print(f" {elapsed:.1f}s → {n_id} matched, {n_null} null{cost_str}",
                  file=sys.stderr, flush=True)

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-input", default="pipeline/agent-input.json")
    parser.add_argument("--bgg", default="boardgames_ranks-*.csv")
    parser.add_argument("--manual", default="pipeline/mappings.yaml")
    parser.add_argument("--agent", default="pipeline/mappings.agent.yaml")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the number of unmatched items processed in this run")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the prompt(s) without invoking claude")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Claude model to use (default: {DEFAULT_MODEL})")
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
        batch_size=ns.batch_size,
        limit=ns.limit,
        dry_run=ns.dry_run,
        model=ns.model,
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
