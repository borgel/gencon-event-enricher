from pipeline.parse_bgg import parse_bgg_csv


def test_parse_bgg_basic(tiny_bgg_path):
    db = parse_bgg_csv(tiny_bgg_path)
    assert len(db.entries_by_id) == 4
    e = db.entries_by_id[342942]
    assert e.name == "Ark Nova"
    assert e.year_published == 2021
    assert e.rank == 2
    assert e.bayesaverage == 8.35507
    assert e.is_expansion is False
    assert e.category_ranks == {"strategygames": 2}


def test_parse_bgg_expansion_flag(tiny_bgg_path):
    db = parse_bgg_csv(tiny_bgg_path)
    asia = db.entries_by_id[266192]
    assert asia.is_expansion is True


def test_normalized_name_index(tiny_bgg_path):
    db = parse_bgg_csv(tiny_bgg_path)
    # index keys are lowercased; values are sets of ids
    assert 342942 in db.ids_by_normalized_name["ark nova"]
    assert 266192 in db.ids_by_normalized_name["wingspan asia"]
