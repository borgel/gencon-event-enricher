from pipeline.parse_gencon import parse_gencon_xlsx
from pipeline.grouping import group_sessions


def test_grouping_collapses_repeat_sessions(tiny_gencon_path):
    sessions = parse_gencon_xlsx(tiny_gencon_path)
    groups = group_sessions(sessions)
    # 5 sessions in fixture: 2 are the same Wingspan tournament -> 4 groups
    assert len(groups) == 4


def test_grouping_canonical_fields(tiny_gencon_path):
    sessions = parse_gencon_xlsx(tiny_gencon_path)
    groups = group_sessions(sessions)
    wingspan = next(g for g in groups if g.title.startswith("Wingspan"))
    assert wingspan.event_type == "BGM"
    assert wingspan.event_type_label == "BGM - Board Game"
    assert len(wingspan.sessions) == 2
    # sorted by start time
    assert wingspan.sessions[0].start < wingspan.sessions[1].start
    assert wingspan.tournament is True


def test_grouping_picks_longest_descriptions(tiny_gencon_path):
    sessions = parse_gencon_xlsx(tiny_gencon_path)
    groups = group_sessions(sessions)
    wingspan = next(g for g in groups if g.title.startswith("Wingspan"))
    # both sessions had identical descriptions, just sanity-check non-empty
    assert wingspan.long_description == "Long desc here."
