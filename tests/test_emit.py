import json
from datetime import datetime
from pipeline.emit import build_events_json, build_agent_input_json
from pipeline.types import EventGroup, SessionRecord, BGGMatch, BGGEntry
from pipeline.matching import MatchResult


def _session(idx: int, start: datetime) -> SessionRecord:
    return SessionRecord(
        gencon_id=f"BGM26ND00000{idx}", group_label="Thursday Games",
        title="Wingspan: Asia Tournament", short_description="",
        long_description="", event_type="BGM - Board Game",
        game_system="Wingspan: Asia", rules_edition="",
        min_players=1, max_players=4,
        age_required="Teen (13+)", experience_required="Some",
        materials_required="No", materials_required_details="",
        start=start, duration_minutes=240,
        end=datetime(start.year, start.month, start.day, start.hour + 4),
        gm_names="Jane Doe", website="", email="", tournament=True,
        round_number=idx, total_rounds=2, minimum_play_time=240,
        attendee_registration="Yes", cost=8.0, location="ICC",
        room="Hall A", table="27", special_category="none",
        tickets_available=8, last_modified=None,
    )


def test_build_events_json_shape():
    g = EventGroup(
        key="BGM-wingspan-asia-tournament-abc123",
        title="Wingspan: Asia Tournament", event_type="BGM",
        event_type_label="BGM - Board Game", game_system="Wingspan: Asia",
        short_description="Compete!", long_description="Long desc.",
        tournament=True, min_players=1, max_players=4,
        age_required="Teen (13+)", experience_required="Some",
        duration_minutes=240, cost=8.0,
        sessions=[_session(1, datetime(2026, 7, 30, 9, 0))],
        bgg=BGGMatch(
            bgg=BGGEntry(
                id=266192, name="Wingspan: Asia", year_published=2022,
                rank=142, bayesaverage=7.84, average=8.05, users_rated=14238,
                is_expansion=True, category_ranks={"strategygames": 44},
            ),
            source="exact",
        ),
    )
    out = build_events_json([g], gencon_source="x.xlsx", bgg_source="y.csv")
    blob = json.loads(out)
    assert blob["meta"]["stats"]["groups"] == 1
    assert blob["meta"]["stats"]["matched"] == 1
    g0 = blob["groups"][0]
    assert g0["key"].startswith("BGM-wingspan-asia-tournament")
    assert g0["bgg"]["id"] == 266192
    assert g0["bgg"]["match_source"] == "exact"
    assert g0["bgg"]["category_ranks"] == {"strategygames": 44}
    assert g0["sessions"][0]["start"] == "2026-07-30T09:00:00"


def test_build_events_json_omits_bgg_when_unmatched():
    g = EventGroup(
        key="SEM-cosplay-101-abc", title="Cosplay 101", event_type="SEM",
        event_type_label="SEM - Seminar", game_system="",
        short_description="", long_description="", tournament=False,
        min_players=1, max_players=50, age_required="", experience_required="",
        duration_minutes=60, cost=2.0,
        sessions=[_session(1, datetime(2026, 7, 31, 10, 0))],
    )
    out = build_events_json([g], gencon_source="x.xlsx", bgg_source="y.csv")
    blob = json.loads(out)
    assert "bgg" not in blob["groups"][0]
    assert blob["meta"]["stats"]["unmatched"] == 1


def test_build_agent_input_json_includes_candidates():
    g = EventGroup(
        key="RPG-hellfire-abc", title="Hellfire", event_type="RPG",
        event_type_label="RPG - Roleplaying Game", game_system="Marvel SH",
        short_description="rpg", long_description="long",
        tournament=False, min_players=3, max_players=8,
        age_required="Teen (13+)", experience_required="None",
        duration_minutes=300, cost=6.0, sessions=[],
    )
    candidates = [
        # (BGGEntry, score)
        (BGGEntry(
            id=200, name="Marvel Super Heroes", year_published=1984,
            rank=None, bayesaverage=None, average=None, users_rated=0,
            is_expansion=False, category_ranks={}), 88.0),
    ]
    out = build_agent_input_json([(g, candidates)])
    blob = json.loads(out)
    item = blob["unmatched"][0]
    assert item["key"] == "RPG-hellfire-abc"
    assert item["title"] == "Hellfire"
    assert item["candidates"][0]["bgg_id"] == 200
    assert item["candidates"][0]["score"] == 88.0
