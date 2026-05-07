"""LLM-driven matching runner for unmatched event groups.

Reads pipeline/agent-input.json (produced by build.py), sends batches to the
Claude CLI via an injectable invoker, validates responses, and appends results
to pipeline/mappings.agent.yaml.
"""
from __future__ import annotations
import argparse
import json
import sys
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


def _slim_bgg_csv(bgg_path: Path) -> str:
    """Read the full BGG CSV but project to only the columns the agent needs.

    Keeping the prompt smaller helps both context size and cost. We include
    id/name/year/bayesaverage/is_expansion. Skip "Not Ranked" -> empty rows is fine.
    """
    out_lines = ["id,name,yearpublished,bayesaverage,is_expansion"]
    import csv
    with open(bgg_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out_lines.append(",".join([
                row["id"], _quote(row["name"]),
                row.get("yearpublished", ""),
                row.get("bayesaverage", ""),
                row.get("is_expansion", "0"),
            ]))
    return "\n".join(out_lines)


def _quote(s: str) -> str:
    if "," in s or '"' in s:
        return '"' + s.replace('"', '""') + '"'
    return s


def run(
    *,
    agent_input_path: Path,
    bgg_path: Path,
    manual_path: Path,
    agent_path: Path,
    invoker: ClaudeInvoker = invoke_claude_cli,
    batch_size: int = 50,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> RunSummary:
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
        return summary

    bgg_csv = _slim_bgg_csv(bgg_path)

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        prompt = build_prompt(batch, bgg_csv)
        if dry_run:
            print(f"--- batch {i // batch_size + 1} ({len(batch)} items) ---")
            print(prompt[:2000] + ("\n…" if len(prompt) > 2000 else ""))
            continue

        for attempt in (1, 2):
            try:
                envelope = invoker(prompt)
                matches = parse_response(envelope)
                break
            except ResponseError as e:
                if attempt == 2:
                    print(f"batch {i // batch_size + 1} rejected after retry: {e}",
                          file=sys.stderr)
                    summary.batches_rejected += 1
                    matches = None
                    break
                print(f"batch {i // batch_size + 1} attempt 1 failed ({e}); retrying once",
                      file=sys.stderr)

        summary.batches_run += 1
        if matches is None:
            continue

        for m in matches:
            agent[m.key] = MappingEntry(
                bgg_id=m.bgg_id,
                note=f"{m.confidence}: {m.reasoning}" if m.reasoning else None,
            )
            summary.mappings_added += 1

        save_mapping(agent_path, agent)

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
    )
    print("Agent runner summary:")
    print(f"  batches_run:           {summary.batches_run}")
    print(f"  batches_rejected:      {summary.batches_rejected}")
    print(f"  mappings_added:        {summary.mappings_added}")
    print(f"  skipped_already_mapped:{summary.skipped_already_mapped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
