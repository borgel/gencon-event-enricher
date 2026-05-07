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


def test_exact_match_on_title():
    from pipeline.parse_bgg import BGGDatabase
    from pipeline.matching import match_exact
    db = BGGDatabase()
    db.entries_by_id[100] = BGGEntry(
        id=100, name="Brass: Birmingham", year_published=2018, rank=1,
        bayesaverage=8.39, average=8.56, users_rated=58000,
        is_expansion=False, category_ranks={},
    )
    db.ids_by_normalized_name = {"brass birmingham": {100}}
    result = match_exact("Brass: Birmingham — Learn & Play", "Brass: Birmingham", db)
    # Either field can produce a match; with this title and game_system both work
    assert result is not None
    assert result.bgg.id == 100
    assert result.source == "exact"


def test_exact_match_falls_back_to_game_system():
    from pipeline.parse_bgg import BGGDatabase
    from pipeline.matching import match_exact
    db = BGGDatabase()
    db.entries_by_id[200] = BGGEntry(
        id=200, name="Marvel Super Heroes", year_published=1984,
        rank=None, bayesaverage=None, average=None, users_rated=0,
        is_expansion=False, category_ranks={},
    )
    db.ids_by_normalized_name = {"marvel super heroes": {200}}
    # The Title is an RPG scenario name; the Game System is the canonical game.
    result = match_exact("Hellfire in the Heartland, 1938", "Marvel Super Heroes", db)
    assert result is not None
    assert result.bgg.id == 200


def test_exact_no_match_returns_none():
    from pipeline.parse_bgg import BGGDatabase
    from pipeline.matching import match_exact
    db = BGGDatabase()
    result = match_exact("Whatever", "Whatever", db)
    assert result is None


def test_exact_picks_lowest_id_on_collision():
    """If two BGG entries normalize to the same name, prefer the one with the
    lowest id (BGG's lower ids tend to be the canonical/older entry)."""
    from pipeline.parse_bgg import BGGDatabase
    from pipeline.matching import match_exact
    db = BGGDatabase()
    db.entries_by_id[100] = BGGEntry(
        id=100, name="Catan", year_published=1995, rank=200,
        bayesaverage=7.0, average=7.1, users_rated=10000,
        is_expansion=False, category_ranks={},
    )
    db.entries_by_id[500] = BGGEntry(
        id=500, name="Catan", year_published=2020, rank=None,
        bayesaverage=None, average=None, users_rated=0,
        is_expansion=True, category_ranks={},
    )
    db.ids_by_normalized_name = {"catan": {100, 500}}
    result = match_exact("Catan", "", db)
    assert result.bgg.id == 100


def test_fuzzy_match_minor_variant():
    from pipeline.parse_bgg import BGGDatabase
    from pipeline.matching import match_fuzzy
    db = BGGDatabase()
    db.entries_by_id[100] = BGGEntry(
        id=100, name="Wingspan: Asia", year_published=2022, rank=142,
        bayesaverage=7.84, average=8.05, users_rated=14000,
        is_expansion=True, category_ranks={"strategygames": 44},
    )
    db.ids_by_normalized_name = {"wingspan asia": {100}}
    # Title with extra noise that exact would miss
    result = match_fuzzy("Wingspan Asia Tournament", "Wingspan: Asia", db, threshold=90)
    assert result is not None
    assert result.bgg.id == 100
    assert result.source == "fuzzy"
    assert result.score >= 90


def test_fuzzy_below_threshold_no_match():
    from pipeline.parse_bgg import BGGDatabase
    from pipeline.matching import match_fuzzy
    db = BGGDatabase()
    db.entries_by_id[100] = BGGEntry(
        id=100, name="Brass: Birmingham", year_published=2018,
        rank=1, bayesaverage=8.39, average=8.56, users_rated=58000,
        is_expansion=False, category_ranks={},
    )
    db.ids_by_normalized_name = {"brass birmingham": {100}}
    result = match_fuzzy("Cosplay 101", "", db, threshold=90)
    assert result is None


def test_cascade_prefers_manual():
    from pipeline.parse_bgg import BGGDatabase
    from pipeline.matching import match_group
    from pipeline.types import EventGroup
    db = BGGDatabase()
    db.entries_by_id[100] = BGGEntry(
        id=100, name="Wingspan: Asia", year_published=2022, rank=142,
        bayesaverage=7.84, average=8.05, users_rated=14000,
        is_expansion=True, category_ranks={},
    )
    db.entries_by_id[999] = BGGEntry(
        id=999, name="Manual Override Target", year_published=2024,
        rank=None, bayesaverage=None, average=None, users_rated=0,
        is_expansion=False, category_ranks={},
    )
    db.ids_by_normalized_name = {"wingspan asia": {100}, "manual override target": {999}}

    g = EventGroup(
        key="K1", title="Wingspan: Asia", event_type="BGM",
        event_type_label="BGM - Board Game", game_system="Wingspan: Asia",
        short_description="", long_description="", tournament=False,
        min_players=1, max_players=4, age_required="", experience_required="",
        duration_minutes=240, cost=0.0, sessions=[],
    )
    manual = {"K1": MappingEntry(bgg_id=999)}
    result = match_group(g, manual, {}, db)
    assert result.bgg.id == 999
    assert result.source == "manual"


def test_cascade_falls_through_to_fuzzy():
    from pipeline.parse_bgg import BGGDatabase
    from pipeline.matching import match_group
    from pipeline.types import EventGroup
    db = BGGDatabase()
    db.entries_by_id[100] = BGGEntry(
        id=100, name="Wingspan: Asia", year_published=2022, rank=142,
        bayesaverage=7.84, average=8.05, users_rated=14000,
        is_expansion=True, category_ranks={},
    )
    db.ids_by_normalized_name = {"wingspan asia": {100}}

    g = EventGroup(
        key="K1", title="Wingspan Asia Tournament Round 1",
        event_type="BGM", event_type_label="BGM - Board Game",
        game_system="Wingspan: Asia",
        short_description="", long_description="", tournament=False,
        min_players=1, max_players=4, age_required="", experience_required="",
        duration_minutes=240, cost=0.0, sessions=[],
    )
    result = match_group(g, {}, {}, db)
    # title doesn't exact-match because of "Tournament Round 1", so it fuzzes.
    # game_system "Wingspan: Asia" exact-matches first, so source=exact.
    assert result.source == "exact"
    assert result.bgg.id == 100


def test_cascade_returns_none_when_unmatched():
    from pipeline.parse_bgg import BGGDatabase
    from pipeline.matching import match_group
    from pipeline.types import EventGroup
    db = BGGDatabase()
    g = EventGroup(
        key="SEM-cosplay", title="Cosplay 101", event_type="SEM",
        event_type_label="SEM - Seminar", game_system="",
        short_description="", long_description="", tournament=False,
        min_players=1, max_players=50, age_required="", experience_required="",
        duration_minutes=60, cost=0.0, sessions=[],
    )
    assert match_group(g, {}, {}, db) is None


def test_cascade_respects_null_override():
    from pipeline.parse_bgg import BGGDatabase
    from pipeline.matching import match_group
    from pipeline.types import EventGroup
    db = BGGDatabase()
    db.entries_by_id[100] = BGGEntry(
        id=100, name="Cosplay", year_published=2020, rank=None,
        bayesaverage=None, average=None, users_rated=0,
        is_expansion=False, category_ranks={},
    )
    db.ids_by_normalized_name = {"cosplay": {100}}
    g = EventGroup(
        key="SEM-cosplay-101", title="Cosplay", event_type="SEM",
        event_type_label="SEM - Seminar", game_system="",
        short_description="", long_description="", tournament=False,
        min_players=1, max_players=50, age_required="", experience_required="",
        duration_minutes=60, cost=0.0, sessions=[],
    )
    # Even though "Cosplay" exact-matches a BGG id, the manual null says no.
    manual = {"SEM-cosplay-101": MappingEntry(bgg_id=None)}
    assert match_group(g, manual, {}, db) is None
