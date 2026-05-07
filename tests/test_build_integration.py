import json
import sys
from pathlib import Path

import pytest

from pipeline.build import build


def test_build_full_pipeline(tmp_path, tiny_gencon_path, tiny_bgg_path):
    docs_data = tmp_path / "docs" / "data"
    pipeline_dir = tmp_path / "pipeline"
    docs_data.mkdir(parents=True)
    pipeline_dir.mkdir()
    (pipeline_dir / "mappings.yaml").write_text("# empty\n")
    (pipeline_dir / "mappings.agent.yaml").write_text("# empty\n")

    summary = build(
        gencon_path=tiny_gencon_path,
        bgg_path=tiny_bgg_path,
        manual_path=pipeline_dir / "mappings.yaml",
        agent_path=pipeline_dir / "mappings.agent.yaml",
        events_out=docs_data / "events.json",
        agent_input_out=pipeline_dir / "agent-input.json",
    )

    blob = json.loads((docs_data / "events.json").read_text())
    assert blob["meta"]["stats"]["groups"] == 4   # 2 wingspan sessions collapsed
    # Wingspan: Asia exact-matches via game_system; Brass: Birmingham exact-matches.
    assert blob["meta"]["stats"]["matched"] >= 2
    # The cosplay seminar and the Marvel-SH RPG should be in agent-input.
    agent_blob = json.loads((pipeline_dir / "agent-input.json").read_text())
    keys = {item["key"] for item in agent_blob["unmatched"]}
    assert any("cosplay" in k.lower() for k in keys)
    assert any("hellfire" in k.lower() for k in keys)


def test_build_summary_shape(tmp_path, tiny_gencon_path, tiny_bgg_path):
    summary = build(
        gencon_path=tiny_gencon_path,
        bgg_path=tiny_bgg_path,
        manual_path=tmp_path / "manual.yaml",
        agent_path=tmp_path / "agent.yaml",
        events_out=tmp_path / "events.json",
        agent_input_out=tmp_path / "agent-input.json",
    )
    assert {"manual", "agent", "exact", "fuzzy", "unmatched", "null_override"} <= set(summary)
