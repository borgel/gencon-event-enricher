from pipeline.normalize import normalize_for_match


def test_lowercase():
    assert normalize_for_match("CATAN") == "catan"


def test_strip_punct_and_collapse_ws():
    assert normalize_for_match(" Brass: Birmingham — Learn & Play! ") == "brass birmingham learn play"


def test_drops_articles():
    # 'the/a/an' at the start are dropped
    assert normalize_for_match("The Resistance") == "resistance"
    assert normalize_for_match("A Game of Thrones") == "game of thrones"


def test_unicode_safe():
    assert normalize_for_match("Pokémon TCG") == "pokemon tcg"


def test_handles_empty_and_none():
    assert normalize_for_match("") == ""
    assert normalize_for_match(None) == ""
