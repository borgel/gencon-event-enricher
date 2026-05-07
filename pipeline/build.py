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
    match_group, match_overrides, match_exact, match_fuzzy,
    fuzzy_top_candidates, MatchResult, NO_OVERRIDE,
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
    fuzzy_threshold: int = 90,
) -> dict[str, int]:
    sessions = parse_gencon_xlsx(gencon_path)
    groups = group_sessions(sessions)
    bgg = parse_bgg_csv(bgg_path)
    manual = load_mapping(manual_path)
    agent = load_mapping(agent_path)

    summary = dict.fromkeys(
        ("manual", "agent", "exact", "fuzzy", "unmatched", "null_override"), 0
    )
    unmatched: list[tuple] = []

    for g in groups:
        result = match_group(g, manual, agent, bgg, fuzzy_threshold=fuzzy_threshold)
        if result is None:
            # Distinguish "null override" from "tried all stages and failed"
            override = match_overrides(g.key, manual, agent, bgg)
            if override is None:
                summary["null_override"] += 1
            else:
                summary["unmatched"] += 1
                unmatched.append((g, fuzzy_top_candidates(g.title, g.game_system, bgg)))
            continue
        summary[result.source] += 1
        from .types import BGGMatch
        g.bgg = BGGMatch(bgg=result.bgg, source=result.source)

    events_out.parent.mkdir(parents=True, exist_ok=True)
    events_out.write_text(build_events_json(
        groups,
        gencon_source=gencon_path.name,
        bgg_source=bgg_path.name,
    ))
    agent_input_out.parent.mkdir(parents=True, exist_ok=True)
    agent_input_out.write_text(build_agent_input_json(unmatched))

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
    parser.add_argument("--fuzzy-threshold", type=int, default=90)
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
