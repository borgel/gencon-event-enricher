"""Compute stable, URL-safe keys for event groups.

A group is "the same event run multiple times". We collapse round numbers,
strip punctuation, and combine with the short event-type code so that
'Wingspan: Asia Tournament — Round 1' and '… Round 2' both map to the same key.
"""
from __future__ import annotations
import hashlib
import re

# Patterns we strip before normalization.
_ROUND_PATTERNS = [
    re.compile(r"\s*[—\-:]\s*round\s*\d+(\s*of\s*\d+)?\s*$", re.IGNORECASE),
    re.compile(r"\s*\(\s*round\s*\d+(\s*of\s*\d+)?\s*\)\s*$", re.IGNORECASE),
    re.compile(r"\s*[—\-:]?\s*rd\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"\s*[—\-:]?\s*pt\.?\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"\s*[—\-:]?\s*part\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"\s*#\s*\d+\s*$"),
]


def short_event_type(label: str) -> str:
    """'BGM - Board Game' -> 'BGM'. Empty / unknown -> 'UNK'."""
    if not label:
        return "UNK"
    head = label.split("-", 1)[0].strip().upper()
    return head or "UNK"


def _strip_round(title: str) -> str:
    prev = None
    while prev != title:
        prev = title
        for p in _ROUND_PATTERNS:
            title = p.sub("", title)
    return title.strip()


def _slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def derive_group_key(event_type: str, title: str, game_system: str) -> str:
    """Stable, URL-safe key for an event group.

    Format: '<TYPE>-<title-slug>[-<system-slug>]-<short-hash>'.
    Hash anchors uniqueness when slugs collide; type-prefix and human-readable
    middle make the key debuggable in mappings.yaml.
    """
    title_clean = _strip_round(title)
    title_slug = _slug(title_clean)
    system_slug = _slug(game_system)
    canonical = f"{event_type}|{title_clean.lower()}|{game_system.lower()}"
    h = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:6]
    parts = [event_type, title_slug]
    if system_slug and system_slug != title_slug:
        parts.append(system_slug)
    parts.append(h)
    return "-".join(p for p in parts if p)
