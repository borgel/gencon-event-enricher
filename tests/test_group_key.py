from pipeline.group_key import derive_group_key, short_event_type


def test_short_event_type_extracts_prefix():
    assert short_event_type("BGM - Board Game") == "BGM"
    assert short_event_type("RPG - Roleplaying Game") == "RPG"
    assert short_event_type("SEM - Seminar") == "SEM"
    assert short_event_type("") == "UNK"


def test_round_numbers_collapse():
    a = derive_group_key("BGM", "Wingspan: Asia Tournament — Round 1", "Wingspan: Asia")
    b = derive_group_key("BGM", "Wingspan: Asia Tournament — Round 2", "Wingspan: Asia")
    c = derive_group_key("BGM", "Wingspan: Asia Tournament Rd 3", "Wingspan: Asia")
    d = derive_group_key("BGM", "Wingspan: Asia Tournament (Round 1 of 4)", "Wingspan: Asia")
    assert a == b == c == d


def test_distinct_titles_distinct_keys():
    a = derive_group_key("BGM", "Wingspan: Asia Tournament", "Wingspan: Asia")
    b = derive_group_key("BGM", "Wingspan: Oceania", "Wingspan: Oceania")
    assert a != b


def test_event_type_distinguishes():
    a = derive_group_key("BGM", "Catan", "Catan")
    b = derive_group_key("RPG", "Catan", "Catan")
    assert a != b


def test_key_is_url_safe():
    k = derive_group_key("BGM", "Brass: Birmingham — Learn & Play!", "Brass: Birmingham")
    assert all(c.isalnum() or c == "-" for c in k)
