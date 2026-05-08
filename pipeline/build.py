"""Build the events.json + agent-input.json artifacts.

Run as a script:

    uv run python pipeline/build.py
        [--gencon ../gencon_events-*.xlsx]
        [--bgg ../boardgames_ranks-*.csv]
"""
from __future__ import annotations
import argparse
import glob
import sys
from pathlib import Path
from typing import Any

from .parse_gencon import parse_gencon_xlsx
from .parse_bgg import parse_bgg_csv
from .grouping import group_sessions
from .mappings import load_mapping
from .matching import (
    match_group, match_overrides, match_fuzzy_all, SORT_THRESHOLD,
)
from .emit import build_events_json, build_agent_input_json


def build(
    *,
    gencon_path: Path,
    bgg_path: Path,
    manual_path: Path,
    agent_path: Path,
    events_out: Path,
    agent_input_out: Path,
    fuzzy_threshold: int = SORT_THRESHOLD,
    verbose: bool = True,
) -> dict[str, int]:
    import time
    def stamp(label: str, t0: float) -> float:
        if verbose:
            print(f"  [{label}] {time.perf_counter() - t0:.1f}s", file=sys.stderr)
        return time.perf_counter()

    t0 = time.perf_counter()
    sessions = parse_gencon_xlsx(gencon_path)
    t0 = stamp(f"parse_gencon ({len(sessions)} sessions)", t0)
    groups = group_sessions(sessions)
    t0 = stamp(f"group_sessions ({len(groups)} groups)", t0)
    bgg = parse_bgg_csv(bgg_path)
    t0 = stamp(f"parse_bgg ({len(bgg.entries_by_id)} entries)", t0)
    manual = load_mapping(manual_path)
    agent = load_mapping(agent_path)
    t0 = stamp("load mappings", t0)

    # Batch-precompute fuzzy matches AND top-N candidates per group via cdist
    # (parallel + SIMD). The top-N is what the agent runner needs for unmatched
    # groups; computing it from the same matrix avoids a second slow pass.
    fuzzy_results, top_candidates_by_key = match_fuzzy_all(
        groups, bgg, sort_threshold=fuzzy_threshold,
    )
    t0 = stamp(f"match_fuzzy_all ({len(fuzzy_results)} matches)", t0)
    def fuzzy_resolver(g):
        return fuzzy_results.get(g.key)

    summary = dict.fromkeys(
        ("manual", "agent", "exact", "fuzzy", "unmatched", "null_override"), 0
    )
    unmatched: list[tuple] = []

    for g in groups:
        result = match_group(
            g, manual, agent, bgg,
            fuzzy_threshold=fuzzy_threshold,
            fuzzy_resolver=fuzzy_resolver,
        )
        if result is None:
            # Distinguish "null override" from "tried all stages and failed"
            override = match_overrides(g.key, manual, agent, bgg)
            if override is None:
                summary["null_override"] += 1
            else:
                summary["unmatched"] += 1
                unmatched.append((g, top_candidates_by_key.get(g.key, [])))
            continue
        summary[result.source] += 1
        from .types import BGGMatch
        g.bgg = BGGMatch(bgg=result.bgg, source=result.source)
    t0 = stamp(f"cascade ({len(unmatched)} unmatched, top_candidates per each)", t0)

    events_out.parent.mkdir(parents=True, exist_ok=True)
    events_out.write_text(build_events_json(
        groups,
        gencon_source=gencon_path.name,
        bgg_source=bgg_path.name,
    ))
    t0 = stamp("write events.json", t0)
    agent_input_out.parent.mkdir(parents=True, exist_ok=True)
    agent_input_out.write_text(build_agent_input_json(unmatched))
    t0 = stamp("write agent-input.json", t0)

    return summary


def _resolve_glob(pattern: str) -> Path:
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"no files match {pattern!r}")
    return Path(matches[-1])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gencon", default="gencon_events-*.xlsx",
                        help="glob; latest matching file is used")
    parser.add_argument("--bgg", default="boardgames_ranks-*.csv",
                        help="glob; latest matching file is used")
    parser.add_argument("--manual", default="pipeline/mappings.yaml")
    parser.add_argument("--agent", default="pipeline/mappings.agent.yaml")
    parser.add_argument("--events-out", default="docs/data/events.json")
    parser.add_argument("--agent-input-out", default="pipeline/agent-input.json")
    parser.add_argument("--fuzzy-threshold", type=int, default=SORT_THRESHOLD,
                        help="token_sort_ratio threshold (default 65)")
    ns = parser.parse_args(argv)

    summary = build(
        gencon_path=_resolve_glob(ns.gencon),
        bgg_path=_resolve_glob(ns.bgg),
        manual_path=Path(ns.manual),
        agent_path=Path(ns.agent),
        events_out=Path(ns.events_out),
        agent_input_out=Path(ns.agent_input_out),
        fuzzy_threshold=ns.fuzzy_threshold,
    )
    print("Match summary:")
    for k, v in summary.items():
        print(f"  {k:>15}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
