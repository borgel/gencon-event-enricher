"""Single source of truth for name normalization used in matching."""
from __future__ import annotations
import re
import unicodedata

_LEADING_ARTICLES = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)


def normalize_for_match(s: str | None) -> str:
    if not s:
        return ""
    # Strip diacritics: Pokémon -> Pokemon
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = _LEADING_ARTICLES.sub("", s).strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()
