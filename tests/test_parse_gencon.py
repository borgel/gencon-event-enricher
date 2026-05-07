from datetime import datetime
from pipeline.parse_gencon import parse_gencon_xlsx


def test_parse_yields_one_record_per_row(tiny_gencon_path):
    rows = parse_gencon_xlsx(tiny_gencon_path)
    assert len(rows) == 5


def test_parse_session_fields(tiny_gencon_path):
    rows = parse_gencon_xlsx(tiny_gencon_path)
    row1 = next(r for r in rows if r.gencon_id == "BGM26ND000001")
    assert row1.title == "Wingspan: Asia Tournament"
    assert row1.event_type == "BGM - Board Game"
    assert row1.game_system == "Wingspan: Asia"
    assert row1.min_players == 1
    assert row1.max_players == 4
    assert row1.tournament is True
    assert row1.cost == 8.0
    assert row1.tickets_available == 8
    assert row1.start == datetime(2026, 7, 30, 9, 0)
    assert row1.end == datetime(2026, 7, 30, 13, 0)


def test_unmatchable_seminar_still_parses(tiny_gencon_path):
    rows = parse_gencon_xlsx(tiny_gencon_path)
    sem = next(r for r in rows if r.gencon_id == "SEM26ND000005")
    assert sem.event_type == "SEM - Seminar"
    assert sem.game_system == ""
