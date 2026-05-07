"""Typed records used throughout the pipeline."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class SessionRecord:
    """One row from the GenCon xlsx — a single scheduled session."""
    gencon_id: str
    group_label: str            # "Group" column, e.g. "Sunday Night Games"
    title: str
    short_description: str
    long_description: str
    event_type: str             # raw, e.g. "BGM - Board Game"
    game_system: str
    rules_edition: str
    min_players: Optional[int]
    max_players: Optional[int]
    age_required: str
    experience_required: str
    materials_required: str
    materials_required_details: str
    start: datetime
    duration_minutes: Optional[int]
    end: datetime
    gm_names: str
    website: str
    email: str
    tournament: bool
    round_number: Optional[int]
    total_rounds: Optional[int]
    minimum_play_time: Optional[int]
    attendee_registration: str
    cost: Optional[float]
    location: str
    room: str
    table: str
    special_category: str
    tickets_available: Optional[int]
    last_modified: Optional[datetime]


@dataclass
class BGGEntry:
    """One game from boardgames_ranks-*.csv."""
    id: int
    name: str
    year_published: Optional[int]
    rank: Optional[int]
    bayesaverage: Optional[float]
    average: Optional[float]
    users_rated: int
    is_expansion: bool
    category_ranks: dict[str, int]   # only populated keys


MatchSource = Literal["manual", "agent", "exact", "fuzzy"]


@dataclass
class BGGMatch:
    bgg: BGGEntry
    source: MatchSource


@dataclass
class EventGroup:
    """One row in the deduplicated output table."""
    key: str
    title: str
    event_type: str            # short code like "BGM"
    event_type_label: str      # original label like "BGM - Board Game"
    game_system: str
    short_description: str
    long_description: str
    tournament: bool
    min_players: Optional[int]
    max_players: Optional[int]
    age_required: str
    experience_required: str
    duration_minutes: Optional[int]
    cost: Optional[float]
    sessions: list[SessionRecord]
    bgg: Optional[BGGMatch] = None
