from pipeline.matching import match_overrides, MatchResult
from pipeline.mappings import MappingEntry
from pipeline.types import BGGEntry


def _bgg_db():
    from pipeline.parse_bgg import BGGDatabase
    db = BGGDatabase()
    db.entries_by_id[100] = BGGEntry(
        id=100, name="Foo", year_published=2020, rank=10,
        bayesaverage=7.5, average=8.0, users_rated=1000,
        is_expansion=False, category_ranks={},
    )
    return db


def test_manual_override_used_when_present():
    manual = {"K1": MappingEntry(bgg_id=100)}
    agent = {}
    result = match_overrides("K1", manual, agent, _bgg_db())
    assert isinstance(result, MatchResult)
    assert result.bgg.id == 100
    assert result.source == "manual"


def test_agent_override_used_when_no_manual():
    manual = {}
    agent = {"K1": MappingEntry(bgg_id=100)}
    result = match_overrides("K1", manual, agent, _bgg_db())
    assert result.bgg.id == 100
    assert result.source == "agent"


def test_manual_wins_over_agent():
    manual = {"K1": MappingEntry(bgg_id=100)}
    agent = {"K1": MappingEntry(bgg_id=999)}  # would be a missing id, but manual wins
    result = match_overrides("K1", manual, agent, _bgg_db())
    assert result.bgg.id == 100
    assert result.source == "manual"


def test_null_override_means_confirmed_no_match():
    manual = {"K1": MappingEntry(bgg_id=None)}
    result = match_overrides("K1", manual, {}, _bgg_db())
    assert result is None    # caller treats None as "no enrichment, but don't try harder"


def test_no_override_returns_sentinel():
    # Distinguish "no override" from "override says no match"
    from pipeline.matching import NO_OVERRIDE
    result = match_overrides("K2", {}, {}, _bgg_db())
    assert result is NO_OVERRIDE
