"""Four-stage matching cascade: overrides → exact → fuzzy."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Final

from .mappings import MappingEntry
from .parse_bgg import BGGDatabase
from .types import BGGEntry, MatchSource


@dataclass
class MatchResult:
    bgg: BGGEntry
    source: MatchSource
    score: float = 100.0   # for fuzzy; 100 for exact/override


# Sentinel: this key has no override entry at all (try later stages).
class _NoOverride:
    pass


NO_OVERRIDE: Final = _NoOverride()


from .normalize import normalize_for_match


def match_overrides(
    key: str,
    manual: dict[str, MappingEntry],
    agent: dict[str, MappingEntry],
    bgg: BGGDatabase,
) -> MatchResult | None | _NoOverride:
    """Resolve from overrides, in priority order: manual then agent.

    Returns:
        MatchResult — override pointed at a real BGG id we know.
        None       — override explicitly said "no BGG match" (don't try further stages).
        NO_OVERRIDE — no override exists; caller should try the next stage.
    """
    for source, table in (("manual", manual), ("agent", agent)):
        if key in table:
            entry = table[key]
            if entry.bgg_id is None:
                return None
            bgg_entry = bgg.entries_by_id.get(entry.bgg_id)
            if bgg_entry is None:
                # The override points at an id that's not in the current BGG dump.
                # Treat as no match for this run, but log via the caller.
                continue
            return MatchResult(bgg=bgg_entry, source=source)
    return NO_OVERRIDE


def match_exact(title: str, game_system: str, bgg: BGGDatabase) -> MatchResult | None:
    """Try Title first, then Game System. Among ties, prefer lower BGG id."""
    for candidate in (title, game_system):
        if not candidate:
            continue
        norm = normalize_for_match(candidate)
        ids = bgg.ids_by_normalized_name.get(norm)
        if ids:
            chosen_id = min(ids)
            return MatchResult(bgg=bgg.entries_by_id[chosen_id], source="exact")
    return None
