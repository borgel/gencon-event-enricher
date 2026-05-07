"""Parse boardgames_ranks-*.csv into an indexed BGG database."""
from __future__ import annotations
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from .types import BGGEntry


CATEGORY_COLS = (
    "abstracts_rank", "cgs_rank", "childrensgames_rank",
    "familygames_rank", "partygames_rank", "strategygames_rank",
    "thematic_rank", "wargames_rank",
)


def _name_normalize(s: str) -> str:
    """Local normalizer for the BGG name index. Task 8 introduces a richer one;
    this is intentionally minimal so parse_bgg has no upward dependency."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def _to_int(v: str) -> int | None:
    v = v.strip()
    if not v or v.lower() == "not ranked":
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _to_float(v: str) -> float | None:
    v = v.strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


@dataclass
class BGGDatabase:
    entries_by_id: dict[int, BGGEntry] = field(default_factory=dict)
    ids_by_normalized_name: dict[str, set[int]] = field(default_factory=dict)


def parse_bgg_csv(path: Path) -> BGGDatabase:
    db = BGGDatabase()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            id_ = int(row["id"])
            cat_ranks = {}
            for col in CATEGORY_COLS:
                rank = _to_int(row.get(col, ""))
                if rank is not None:
                    cat_ranks[col.removesuffix("_rank")] = rank
            entry = BGGEntry(
                id=id_,
                name=row["name"],
                year_published=_to_int(row.get("yearpublished", "")),
                rank=_to_int(row.get("rank", "")),
                bayesaverage=_to_float(row.get("bayesaverage", "")),
                average=_to_float(row.get("average", "")),
                users_rated=_to_int(row.get("usersrated", "")) or 0,
                is_expansion=row.get("is_expansion", "0").strip() == "1",
                category_ranks=cat_ranks,
            )
            db.entries_by_id[id_] = entry
            key = _name_normalize(entry.name)
            db.ids_by_normalized_name.setdefault(key, set()).add(id_)
    return db
