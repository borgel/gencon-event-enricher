from pipeline.agent_prompt import build_prompt


SAMPLE_BATCH = [
    {
        "key": "SEM-cosplay-foam-form-abc",
        "title": "Cosplay 101: Foam & Form",
        "event_type": "SEM",
        "event_type_label": "SEM - Seminar",
        "game_system": "",
        "short_description": "Learn foam-armor basics.",
        "candidates": [],
    },
    {
        "key": "RPG-hellfire-1938-def",
        "title": "Hellfire in the Heartland, 1938",
        "event_type": "RPG",
        "event_type_label": "RPG - Roleplaying Game",
        "game_system": "Marvel Super Heroes",
        "short_description": "Play heroes.",
        "candidates": [
            {"bgg_id": 200, "name": "Marvel Super Heroes", "year": 1984, "score": 88.0}
        ],
    },
]

SAMPLE_BGG_CSV = """\
id,name,yearpublished,bayesaverage,is_expansion
200,Marvel Super Heroes,1984,5.5,0
266192,Wingspan: Asia,2022,7.84,1
"""


def test_prompt_contains_required_sections():
    p = build_prompt(SAMPLE_BATCH, SAMPLE_BGG_CSV)
    # Schema mention so the model knows the contract
    assert "matches" in p
    assert "bgg_id" in p
    # Batch keys appear
    assert "SEM-cosplay-foam-form-abc" in p
    assert "RPG-hellfire-1938-def" in p
    # BGG list appears
    assert "Wingspan: Asia" in p
    # Confidence enum hint
    assert "high" in p and "medium" in p and "low" in p


def test_prompt_is_deterministic():
    p1 = build_prompt(SAMPLE_BATCH, SAMPLE_BGG_CSV)
    p2 = build_prompt(SAMPLE_BATCH, SAMPLE_BGG_CSV)
    assert p1 == p2
