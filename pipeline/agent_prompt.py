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

    SCOPE — VERY IMPORTANT:
    The BGG data we have is the BOARD GAME database (bg_ranks dump). It
    contains: board games, card games, miniatures games (Warhammer, etc.),
    and their expansions. It does NOT contain:
    - Roleplaying games (D&D, Pathfinder, Daggerheart, Cy_Borg, Mörk Borg,
      Call of Cthulhu, Vampire, Shadowrun, FATE, GURPS, Hero System, etc.).
      RPGs are a different BGG database we don't have access to.
    - Seminars, panels, workshops, art shows, autograph sessions, dance
      parties, cosplay events, painting/crafting sessions, kids' activities
      that aren't a specific game.
    - Most LARP and live-action events.

    For ANY event in the above categories, return bgg_id: null with
    confidence "high". The event's `event_type_label` is your strongest
    hint — anything starting with "RPG", "SEM", "TRD", "LRP", "WKS", or
    "MHE" (miniatures hobby/painting events) is almost certainly null.

    Inputs:
    - A CSV of popular BGG entries (id, name, yearpublished, bayesaverage,
      is_expansion).
    - For each batch, an optional CSV of additional BGG entries that fuzzy
      matching surfaced as candidates for events in this batch.
    - A list of unmatched GenCon event groups. Each has a stable `key`, the
      event title, event type label, game system, a short description, and
      up to 5 fuzzy-match candidates ranked by score. A high fuzzy score
      does NOT mean a real match — fuzzy is noisy and surfaces substring
      coincidences (e.g., "The Night" matches anything with "night" in it).

    For each event, decide:
    - If the event_type is RPG/SEM/TRD/LRP/WKS/MHE → bgg_id: null, high.
    - If the event clearly IS a board/card/miniatures game in the BGG
      list provided (matched by full game name, NOT a substring), return
      that BGG id. Use the title and game_system fields to determine
      what game the event is actually about.
    - Otherwise, prefer null over a guess. A wrong id is worse than null.

    Confidence — REPORT IT HONESTLY:
    - "high": you are certain. Use this when the event explicitly names a
      BGG entry (e.g., title or game_system contains the canonical name),
      OR when an obvious-null rule applies (RPG/SEM/TRD/etc.).
    - "medium": probable but not verified. Use sparingly.
    - "low": you guessed or had to break a tie. ALWAYS use "low" if you
      are returning a bgg_id you wouldn't bet $100 on. We would much
      rather have a "low: null" than a "high: wrong_id" — null entries
      are easy to revisit later, while a confidently-wrong id silently
      contaminates the dataset.

    A high fuzzy score (e.g. 100) on a candidate is NOT enough evidence
    by itself — fuzzy scores are token-overlap, so "Operation" matches
    "Operation Virus Bomb (Warhammer 40K)" with score 100 even though
    they are unrelated. Verify the candidate name actually corresponds
    to the game described in the event before using it.

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
