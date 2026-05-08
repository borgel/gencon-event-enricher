"""Four-stage matching cascade: overrides → exact → fuzzy."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Final, Optional

import numpy as np
from rapidfuzz import process, fuzz

from .mappings import MappingEntry
from .normalize import normalize_for_match
from .parse_bgg import BGGDatabase
from .types import BGGEntry, EventGroup, MatchSource


# Compound-rule thresholds for fuzzy matching.
#
# Stage 1 (token_set_ratio >= SET_THRESHOLD): generous, fast candidate finder.
#   token_set_ratio scores 100 when one token list is a subset of the other,
#   so this is a sieve, not a verdict.
# Stage 2 (token_sort_ratio >= SORT_THRESHOLD): the verdict. Sorts both token
#   lists and runs a Levenshtein ratio over the joined strings, so extra
#   tokens DO penalize the score. Catches the "Catan" -> "Catan: Cities &
#   Knights" subset bug that token_set_ratio alone misses.
SET_THRESHOLD: Final = 90
SORT_THRESHOLD: Final = 65


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
    title: str,
    game_system: str,
    bgg: BGGDatabase,
    *,
    threshold: int = SORT_THRESHOLD,
) -> MatchResult | None:
    """Compound-rule fuzzy match for a single group.

    Two-stage scoring:
      1. token_set_ratio >= SET_THRESHOLD picks a candidate (cheap, generous).
      2. token_sort_ratio >= threshold verifies (penalizes extra tokens).

    See module-level docstring for SET_THRESHOLD/SORT_THRESHOLD context.
    Reported score is the token_sort_ratio (the verdict scorer).

    For batch use over thousands of groups, prefer `match_fuzzy_all`, which
    uses cdist + multithreading instead of per-group extractOne.
    """
    candidates = list(bgg.ids_by_normalized_name.keys())
    if not candidates:
        return None

    best_sort_score = -1.0
    best_norm = None
    for q in (title, game_system):
        q_norm = normalize_for_match(q)
        if not q_norm:
            continue
        result = process.extractOne(q_norm, candidates, scorer=fuzz.token_set_ratio)
        if result is None:
            continue
        match_str, set_score, _ = result
        if set_score < SET_THRESHOLD:
            continue
        sort_score = fuzz.token_sort_ratio(q_norm, match_str)
        if sort_score < threshold:
            continue
        if sort_score > best_sort_score:
            best_sort_score = sort_score
            best_norm = match_str

    if best_norm is None:
        return None
    chosen_id = min(bgg.ids_by_normalized_name[best_norm])
    return MatchResult(
        bgg=bgg.entries_by_id[chosen_id],
        source="fuzzy",
        score=float(best_sort_score),
    )


def match_fuzzy_all(
    groups: list[EventGroup],
    bgg: BGGDatabase,
    *,
    sort_threshold: int = SORT_THRESHOLD,
    top_n: int = 5,
    chunk_size: int = 1000,
) -> tuple[dict[str, MatchResult], dict[str, list[tuple[BGGEntry, float]]]]:
    """Batch fuzzy matching for many groups, parallelized via rapidfuzz.cdist.

    Returns a tuple `(matched, top_candidates)`:
      - `matched`: dict keyed by `group.key` containing groups that passed
        the compound-rule (token_set_ratio >= SET_THRESHOLD AND
        token_sort_ratio >= sort_threshold).
      - `top_candidates`: dict keyed by `group.key` mapping to the top-N
        BGG candidates by token_set_ratio, regardless of threshold. Used
        for the agent-input file. Computed from the same cdist matrix as
        the matching, so it's free.

    Implementation:
      - Collect (group_idx, field, normalized_query) for every non-empty
        title/game_system across all groups.
      - In chunks (to bound peak memory), build the M×N token_set_ratio
        matrix via `process.cdist(..., workers=-1)`. cdist parallelizes
        across CPU cores and uses SIMD; this is ~10x faster than calling
        extractOne per query for large M.
      - For each query row: take argmax for matching (compound rule), and
        argpartition for top-N candidates. Both operations reuse the same
        matrix.
      - Resolve per group: across both fields, keep the highest sort score
        for matching, and merge the top-N candidates by candidate index.
    """
    candidates = list(bgg.ids_by_normalized_name.keys())
    if not candidates:
        return {}, {}

    queries: list[str] = []
    sources: list[tuple[int, str]] = []
    for i, g in enumerate(groups):
        for field in ("title", "game_system"):
            q_norm = normalize_for_match(getattr(g, field))
            if q_norm:
                queries.append(q_norm)
                sources.append((i, field))
    if not queries:
        return {}, {}

    n_cands = len(candidates)
    effective_top_n = min(top_n, n_cands)

    # Per-query: (cand_idx, sort_score) after compound rule, or None.
    per_query_match: list[Optional[tuple[int, float]]] = [None] * len(queries)
    # Per-query: list of (cand_idx, set_score) for the top-N rows.
    per_query_top: list[list[tuple[int, int]]] = [[] for _ in range(len(queries))]

    for chunk_start in range(0, len(queries), chunk_size):
        chunk = queries[chunk_start : chunk_start + chunk_size]
        # Stage 1: parallel token_set_ratio matrix.
        matrix = process.cdist(
            chunk, candidates, scorer=fuzz.token_set_ratio,
            workers=-1, dtype=np.uint8,
        )
        best_idx = matrix.argmax(axis=1)
        best_set = matrix.max(axis=1)
        for i in range(len(chunk)):
            row = matrix[i]
            cand_idx = int(best_idx[i])
            set_score = int(best_set[i])

            # Top-N per query (always, even for matched groups — the agent
            # only sees these for unmatched ones, but it costs ~nothing).
            if effective_top_n >= n_cands:
                top_indices = np.argsort(row)[::-1][:effective_top_n]
            else:
                # argpartition is O(n) and gets the top-N unsorted; then
                # argsort just those N. Faster than full argsort for small N.
                cand_part = np.argpartition(row, -effective_top_n)[-effective_top_n:]
                top_indices = cand_part[np.argsort(row[cand_part])[::-1]]
            per_query_top[chunk_start + i] = [
                (int(idx), int(row[idx])) for idx in top_indices
            ]

            # Match decision (compound rule).
            if set_score < SET_THRESHOLD:
                continue
            sort_score = float(fuzz.token_sort_ratio(chunk[i], candidates[cand_idx]))
            if sort_score < sort_threshold:
                continue
            per_query_match[chunk_start + i] = (cand_idx, sort_score)

    # Resolve matches per group: keep best sort_score across both fields.
    by_group_match: dict[str, tuple[int, float]] = {}
    by_group_top: dict[str, dict[int, int]] = {}  # key -> {cand_idx: best_set_score}
    for query_idx in range(len(queries)):
        group_idx, _field = sources[query_idx]
        key = groups[group_idx].key

        hit = per_query_match[query_idx]
        if hit is not None:
            cand_idx, score = hit
            existing = by_group_match.get(key)
            if existing is None or score > existing[1]:
                by_group_match[key] = (cand_idx, score)

        merged = by_group_top.setdefault(key, {})
        for cand_idx, set_score in per_query_top[query_idx]:
            if cand_idx not in merged or set_score > merged[cand_idx]:
                merged[cand_idx] = set_score

    matched: dict[str, MatchResult] = {}
    for key, (cand_idx, score) in by_group_match.items():
        cand_name = candidates[cand_idx]
        chosen_id = min(bgg.ids_by_normalized_name[cand_name])
        matched[key] = MatchResult(
            bgg=bgg.entries_by_id[chosen_id], source="fuzzy", score=score,
        )

    top_candidates: dict[str, list[tuple[BGGEntry, float]]] = {}
    for key, cand_scores in by_group_top.items():
        sorted_pairs = sorted(cand_scores.items(), key=lambda x: -x[1])[:top_n]
        top_candidates[key] = [
            (bgg.entries_by_id[min(bgg.ids_by_normalized_name[candidates[cand_idx]])],
             float(score))
            for cand_idx, score in sorted_pairs
        ]

    return matched, top_candidates


def fuzzy_top_candidates(
    title: str, game_system: str, bgg: BGGDatabase, *, n: int = 5
) -> list[tuple[BGGEntry, float]]:
    """Top-n candidates with scores, regardless of threshold.

    Used for the agent-input file, which wants the most permissive ranking
    so the LLM has useful context. Uses token_set_ratio (most generous) for
    candidate finding so subset/abbreviation cases still surface.
    """
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
    by_name: dict[str, float] = {}
    for n_, sc in pairs:
        if n_ not in by_name or sc > by_name[n_]:
            by_name[n_] = sc
    sorted_pairs = sorted(by_name.items(), key=lambda x: -x[1])[:n]
    return [
        (bgg.entries_by_id[min(bgg.ids_by_normalized_name[name])], score)
        for name, score in sorted_pairs
    ]


FuzzyResolver = Callable[[EventGroup], Optional[MatchResult]]


def match_group(
    group: EventGroup,
    manual: dict[str, MappingEntry],
    agent: dict[str, MappingEntry],
    bgg: BGGDatabase,
    *,
    fuzzy_threshold: int = SORT_THRESHOLD,
    fuzzy_resolver: Optional[FuzzyResolver] = None,
) -> MatchResult | None:
    """Run the four-stage cascade. Returns None if no match (or null override).

    If `fuzzy_resolver` is provided, the cascade calls it to resolve the
    fuzzy stage instead of running `match_fuzzy` per group. Use this for
    batch builds where `match_fuzzy_all` has already produced the answers.
    """
    override = match_overrides(group.key, manual, agent, bgg)
    if override is None:           # null override: confirmed no match
        return None
    if isinstance(override, MatchResult):
        return override
    exact = match_exact(group.title, group.game_system, bgg)
    if exact is not None:
        return exact
    if fuzzy_resolver is not None:
        return fuzzy_resolver(group)
    return match_fuzzy(group.title, group.game_system, bgg, threshold=fuzzy_threshold)
