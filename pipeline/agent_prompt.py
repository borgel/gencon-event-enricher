"""Build a single Claude prompt that asks for BGG matches for a batch of events.

The prompt is structured as two parts (stable prefix + per-batch suffix) so
that Claude's automatic prompt cache can reuse the prefix across batches in
a single run. The savings are 10×+ on cache_read vs cache_creation tokens.
"""
from __future__ import annotations
import json
from textwrap import dedent
from typing import Any

SYSTEM_INSTRUCTIONS = dedent("""\
    You are mapping GenCon events to BoardGameGeek (BGG) entries.

    Inputs:
    - A CSV of popular BGG entries (id, name, yearpublished, bayesaverage,
      is_expansion). This is a curated subset of the BGG database covering
      the most-rated games.
    - For each batch, an optional CSV of additional BGG entries that fuzzy
      matching surfaced as candidates for events in this batch (these may
      not appear in the popular list).
    - A list of unmatched GenCon event groups. Each has a stable `key`, the
      event title, event type label, game system (often the canonical game
      name for RPGs and miniatures games), a short description, and up to 5
      fuzzy-match candidates from the BGG list ranked by score.

    For each event, decide:
    - If the event clearly maps to a BGG entry, return that entry's id.
    - If the event is not a tabletop game and has no BGG entry (cosplay,
      seminars, dance parties, art shows, autograph sessions, video games,
      escape rooms unless they have a BGG entry, etc.), return bgg_id: null.
    - If you genuinely cannot decide, prefer null with confidence "low".

    Use the fuzzy candidates as a starting hint, but verify against the
    BGG entries provided. Prefer non-expansion entries when both a base
    game and an expansion match (unless the event title clearly names the
    expansion).

    Respond ONLY with a JSON object matching this exact schema (no prose,
    no markdown fences):

    {
      "matches": [
        {
          "key": "<the same key from the input>",
          "bgg_id": <integer or null>,
          "confidence": "high" | "medium" | "low",
          "reasoning": "<one sentence, max 500 chars>"
        }
      ]
    }

    Include exactly one match object per input event. The `key` must
    match the input key character-for-character.
""")


def build_stable_prefix(popular_bgg_csv: str) -> str:
    """The cacheable prefix: system instructions + popular BGG list.

    Identical across all batches in a run, so Claude's prompt cache reuses it.
    """
    return "\n".join([
        SYSTEM_INSTRUCTIONS.strip(),
        "",
        "## Popular BGG entries (CSV):",
        "```csv",
        popular_bgg_csv.strip(),
        "```",
        "",
    ])


def build_batch_suffix(
    batch: list[dict[str, Any]], extra_bgg_csv: str | None = None
) -> str:
    """Per-batch suffix: any candidate BGG entries that didn't make the popular
    cut, plus the events to match. Differs per batch by design."""
    parts: list[str] = []
    if extra_bgg_csv and extra_bgg_csv.strip():
        parts.extend([
            "## Additional candidate BGG entries for this batch (CSV):",
            "```csv",
            extra_bgg_csv.strip(),
            "```",
            "",
        ])
    parts.extend([
        "## Events to match:",
        "```json",
        json.dumps(batch, indent=2, ensure_ascii=False, sort_keys=True),
        "```",
        "",
        "Return only the JSON response. Begin now.",
    ])
    return "\n".join(parts)


def build_prompt(
    batch: list[dict[str, Any]],
    popular_bgg_csv: str,
    extra_bgg_csv: str | None = None,
) -> str:
    """Compose the cacheable prefix and the per-batch suffix into one prompt."""
    return build_stable_prefix(popular_bgg_csv) + build_batch_suffix(batch, extra_bgg_csv)
