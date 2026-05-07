"""Serialize the in-memory pipeline state to JSON outputs."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any

from .types import EventGroup, SessionRecord, BGGEntry


def _session_to_dict(s: SessionRecord) -> dict[str, Any]:
    return {
        "gencon_id": s.gencon_id,
        "start": s.start.isoformat() if s.start else None,
        "end": s.end.isoformat() if s.end else None,
        "duration_minutes": s.duration_minutes,
        "location": s.location,
        "room": s.room,
        "table": s.table,
        "gm": s.gm_names,
        "tickets_available": s.tickets_available,
        "round_number": s.round_number,
        "total_rounds": s.total_rounds,
        "cost_override": s.cost,   # session-level cost; group-level cost is canonical
    }


def _bgg_to_dict(e: BGGEntry, *, source: str) -> dict[str, Any]:
    return {
        "id": e.id,
        "name": e.name,
        "year_published": e.year_published,
        "rank": e.rank,
        "bayesaverage": e.bayesaverage,
        "average": e.average,
        "users_rated": e.users_rated,
        "is_expansion": e.is_expansion,
        "category_ranks": e.category_ranks,
        "match_source": source,
    }


def _group_to_dict(g: EventGroup) -> dict[str, Any]:
    out: dict[str, Any] = {
        "key": g.key,
        "title": g.title,
        "event_type": g.event_type,
        "event_type_label": g.event_type_label,
        "game_system": g.game_system,
        "short_description": g.short_description,
        "long_description": g.long_description,
        "tournament": g.tournament,
        "min_players": g.min_players,
        "max_players": g.max_players,
        "age_required": g.age_required,
        "experience_required": g.experience_required,
        "duration_minutes": g.duration_minutes,
        "cost": g.cost,
        "sessions": [_session_to_dict(s) for s in g.sessions],
    }
    if g.bgg is not None:
        out["bgg"] = _bgg_to_dict(g.bgg.bgg, source=g.bgg.source)
    return out


def build_events_json(
    groups: list[EventGroup], *, gencon_source: str, bgg_source: str
) -> str:
    matched = sum(1 for g in groups if g.bgg is not None)
    blob = {
        "groups": [_group_to_dict(g) for g in groups],
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "gencon_source": gencon_source,
            "bgg_source": bgg_source,
            "stats": {
                "groups": len(groups),
                "sessions": sum(len(g.sessions) for g in groups),
                "matched": matched,
                "unmatched": len(groups) - matched,
            },
        },
    }
    return json.dumps(blob, indent=2, ensure_ascii=False)


def build_agent_input_json(
    items: list[tuple[EventGroup, list[tuple[BGGEntry, float]]]],
) -> str:
    return json.dumps({
        "unmatched": [
            {
                "key": g.key,
                "title": g.title,
                "event_type": g.event_type,
                "event_type_label": g.event_type_label,
                "game_system": g.game_system,
                "short_description": g.short_description,
                "candidates": [
                    {"bgg_id": e.id, "name": e.name, "year": e.year_published, "score": score}
                    for e, score in candidates
                ],
            }
            for g, candidates in items
        ],
    }, indent=2, ensure_ascii=False)
