"""Four-stage matching cascade: overrides → exact → fuzzy."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Final

from rapidfuzz import process, fuzz

from .mappings import MappingEntry
from .normalize import normalize_for_match
from .parse_bgg import BGGDatabase
from .types import BGGEntry, EventGroup, MatchSource


@dataclass
class MatchResult:
    bgg: BGGEntry
    source: MatchSource
    score: float = 100.0   # for fuzzy; 100 for exact/override


# Sentinel: this key has no override entry at all (try later stages).
class _NoOverride:
    pass


NO_OVERRIDE: Final = _NoOverride()


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


def match_fuzzy(
    title: str, game_system: str, bgg: BGGDatabase, *, threshold: int = 90
) -> MatchResult | None:
    """Pick the highest-scoring BGG name across (title, game_system) using
    token_set_ratio. Below threshold, return None."""
    candidates = list(bgg.ids_by_normalized_name.keys())
    if not candidates:
        return None

    best_score = -1.0
    best_norm = None
    for q in (title, game_system):
        q_norm = normalize_for_match(q)
        if not q_norm:
            continue
        result = process.extractOne(q_norm, candidates, scorer=fuzz.token_set_ratio)
        if result is None:
            continue
        match_str, score, _ = result
        if score > best_score:
            best_score = score
            best_norm = match_str

    if best_norm is None or best_score < threshold:
        return None

    chosen_id = min(bgg.ids_by_normalized_name[best_norm])
    return MatchResult(
        bgg=bgg.entries_by_id[chosen_id],
        source="fuzzy",
        score=float(best_score),
    )


def fuzzy_top_candidates(
    title: str, game_system: str, bgg: BGGDatabase, *, n: int = 5
) -> list[tuple[BGGEntry, float]]:
    """Top-n candidates with scores, regardless of threshold. Used for agent input."""
    candidates = list(bgg.ids_by_normalized_name.keys())
    if not candidates:
        return []
    pairs: list[tuple[str, float]] = []
    for q in (title, game_system):
        q_norm = normalize_for_match(q)
        if not q_norm:
            continue
        results = process.extract(q_norm, candidates, scorer=fuzz.token_set_ratio, limit=n)
        for match_str, score, _ in results:
            pairs.append((match_str, float(score)))
    # Dedupe by name, keep best score
    by_name: dict[str, float] = {}
    for n_, sc in pairs:
        if n_ not in by_name or sc > by_name[n_]:
            by_name[n_] = sc
    sorted_pairs = sorted(by_name.items(), key=lambda x: -x[1])[:n]
    return [
        (bgg.entries_by_id[min(bgg.ids_by_normalized_name[name])], score)
        for name, score in sorted_pairs
    ]


def match_group(
    group: EventGroup,
    manual: dict[str, MappingEntry],
    agent: dict[str, MappingEntry],
    bgg: BGGDatabase,
    *,
    fuzzy_threshold: int = 90,
) -> MatchResult | None:
    """Run the four-stage cascade. Returns None if no match (or null override)."""
    override = match_overrides(group.key, manual, agent, bgg)
    if override is None:           # null override: confirmed no match
        return None
    if isinstance(override, MatchResult):
        return override
    # NO_OVERRIDE — try exact, then fuzzy.
    exact = match_exact(group.title, group.game_system, bgg)
    if exact is not None:
        return exact
    return match_fuzzy(group.title, group.game_system, bgg, threshold=fuzzy_threshold)
