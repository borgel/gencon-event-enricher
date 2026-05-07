"""Build a single Claude prompt that asks for BGG matches for a batch of events."""
from __future__ import annotations
import json
from textwrap import dedent
from typing import Any

SYSTEM_INSTRUCTIONS = dedent("""\
    You are mapping GenCon events to BoardGameGeek (BGG) entries.

    Inputs:
    - A CSV of all known BGG entries (id, name, yearpublished, bayesaverage, is_expansion).
    - A list of unmatched GenCon event groups. Each has a stable `key`, the event title,
      event type label, game system (often the canonical game name for RPGs and
      miniatures games), a short description, and up to 5 fuzzy-match candidates from
      the BGG list ranked by score.

    For each event, decide:
    - If the event clearly maps to a BGG entry, return that entry's id.
    - If the event is not a tabletop game and has no BGG entry (cosplay,
      seminars, dance parties, art shows, autograph sessions, video games,
      escape rooms unless they have a BGG entry, etc.), return bgg_id: null.
    - If you genuinely cannot decide, prefer null with confidence "low".

    Use the fuzzy candidates as a starting hint, but verify against the
    BGG list. Prefer non-expansion entries when both a base game and an
    expansion match (unless the event title clearly names the expansion).

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


def build_prompt(batch: list[dict[str, Any]], bgg_csv: str) -> str:
    parts = [
        SYSTEM_INSTRUCTIONS.strip(),
        "",
        "## BGG entries (CSV):",
        "```csv",
        bgg_csv.strip(),
        "```",
        "",
        "## Events to match:",
        "```json",
        json.dumps(batch, indent=2, ensure_ascii=False, sort_keys=True),
        "```",
        "",
        "Return only the JSON response. Begin now.",
    ]
    return "\n".join(parts)
