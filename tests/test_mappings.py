from pipeline.mappings import load_mapping, save_mapping, MappingEntry


def test_load_empty_yaml(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("# overrides\n")
    result = load_mapping(p)
    assert result == {}


def test_save_and_load_roundtrip(tmp_path):
    p = tmp_path / "m.yaml"
    save_mapping(p, {
        "BGM-wingspan-asia": MappingEntry(bgg_id=266192, note=None),
        "SEM-cosplay": MappingEntry(bgg_id=None, note="not a board game"),
    })
    result = load_mapping(p)
    assert result["BGM-wingspan-asia"].bgg_id == 266192
    assert result["SEM-cosplay"].bgg_id is None
    assert result["SEM-cosplay"].note == "not a board game"


def test_save_preserves_existing_comments(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        "# Hand-curated overrides — be careful editing.\n"
        "BGM-foo: 12345  # this one verified by hand\n"
    )
    existing = load_mapping(p)
    existing["BGM-bar"] = MappingEntry(bgg_id=99999, note=None)
    save_mapping(p, existing)
    text = p.read_text()
    assert "# Hand-curated overrides" in text
    assert "this one verified by hand" in text
    assert "BGM-bar" in text
