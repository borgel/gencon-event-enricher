"""Collapse SessionRecord rows into EventGroup rows."""
from __future__ import annotations
from collections import defaultdict

from .types import EventGroup, SessionRecord
from .group_key import derive_group_key, short_event_type


def group_sessions(sessions: list[SessionRecord]) -> list[EventGroup]:
    by_key: dict[str, list[SessionRecord]] = defaultdict(list)
    for s in sessions:
        et_short = short_event_type(s.event_type)
        key = derive_group_key(et_short, s.title, s.game_system)
        by_key[key].append(s)

    groups: list[EventGroup] = []
    for key, members in by_key.items():
        # Members are sorted by start time so sessions[0] is the first occurrence.
        members.sort(key=lambda s: s.start or 0)
        canon = members[0]
        et_short = short_event_type(canon.event_type)

        def longest(attr: str) -> str:
            return max((getattr(s, attr) for s in members), key=len)

        groups.append(EventGroup(
            key=key,
            title=canon.title,
            event_type=et_short,
            event_type_label=canon.event_type,
            game_system=canon.game_system,
            short_description=longest("short_description"),
            long_description=longest("long_description"),
            tournament=any(s.tournament for s in members),
            min_players=canon.min_players,
            max_players=canon.max_players,
            age_required=canon.age_required,
            experience_required=canon.experience_required,
            duration_minutes=canon.duration_minutes,
            cost=canon.cost,
            sessions=members,
        ))
    # Default sort: earliest session start.
    groups.sort(key=lambda g: g.sessions[0].start or 0)
    return groups
