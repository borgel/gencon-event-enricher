"""Read/write the human-curated and agent-suggested mapping YAML files.

Format:
    # comments allowed
    BGM-wingspan-asia: 266192       # bgg id
    SEM-cosplay: null               # confirmed no BGG match
    BGM-with-note:
      bgg_id: 12345
      note: "matched by hand 2026-05-04"

The terse 'key: id' form is preferred for hand editing; the dict form lets the
agent attach a note.
"""
from __future__ import annotations
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Optional

from ruamel.yaml import YAML

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=4, offset=2)


@dataclass
class MappingEntry:
    bgg_id: Optional[int]   # None = confirmed no BGG match
    note: Optional[str] = None


def load_mapping(path: Path) -> dict[str, MappingEntry]:
    if not path.exists():
        return {}
    text = path.read_text()
    if not text.strip():
        return {}
    raw = _yaml.load(text) or {}
    out: dict[str, MappingEntry] = {}
    for key, value in raw.items():
        if value is None:
            out[key] = MappingEntry(bgg_id=None)
        elif isinstance(value, int):
            out[key] = MappingEntry(bgg_id=value)
        elif isinstance(value, dict):
            out[key] = MappingEntry(
                bgg_id=value.get("bgg_id"),
                note=value.get("note"),
            )
        else:
            raise ValueError(f"unparseable mapping for {key!r}: {value!r}")
    return out


def save_mapping(path: Path, mapping: dict[str, MappingEntry]) -> None:
    """Round-trip-friendly save: existing comments preserved by mutating the
    parsed document in place when possible."""
    if path.exists() and path.read_text().strip():
        doc = _yaml.load(path.read_text()) or {}
    else:
        from ruamel.yaml.comments import CommentedMap
        doc = CommentedMap()

    # Drop entries no longer in mapping.
    for k in list(doc.keys()):
        if k not in mapping:
            del doc[k]
    # Add/update.
    for k, entry in mapping.items():
        if entry.note:
            from ruamel.yaml.comments import CommentedMap
            sub = CommentedMap()
            sub["bgg_id"] = entry.bgg_id
            sub["note"] = entry.note
            doc[k] = sub
        else:
            doc[k] = entry.bgg_id

    buf = StringIO()
    _yaml.dump(doc, buf)
    path.write_text(buf.getvalue())
