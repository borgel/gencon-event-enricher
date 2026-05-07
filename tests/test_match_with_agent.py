import json
from pathlib import Path
from pipeline.match_with_agent import run, RunSummary
from pipeline.mappings import load_mapping


def _agent_input(tmp_path: Path) -> Path:
    p = tmp_path / "agent-input.json"
    p.write_text(json.dumps({
        "unmatched": [
            {"key": "K1", "title": "T1", "event_type": "RPG",
             "event_type_label": "RPG - Roleplaying Game", "game_system": "Foo",
             "short_description": "", "candidates": []},
            {"key": "K2", "title": "T2", "event_type": "SEM",
             "event_type_label": "SEM - Seminar", "game_system": "",
             "short_description": "", "candidates": []},
        ]
    }))
    return p


def _bgg_csv(tmp_path: Path) -> Path:
    p = tmp_path / "bgg.csv"
    p.write_text(
        "id,name,yearpublished,rank,bayesaverage,average,usersrated,is_expansion,abstracts_rank,cgs_rank,childrensgames_rank,familygames_rank,partygames_rank,strategygames_rank,thematic_rank,wargames_rank\n"
        "100,Foo,2020,200,7.0,7.5,1000,0,,,,,,200,,\n"
    )
    return p


def test_run_writes_agent_yaml(tmp_path):
    agent_input = _agent_input(tmp_path)
    bgg = _bgg_csv(tmp_path)
    agent_yaml = tmp_path / "mappings.agent.yaml"
    manual_yaml = tmp_path / "mappings.yaml"

    def fake_invoker(prompt: str) -> str:
        return json.dumps({
            "type": "result",
            "result": json.dumps({
                "matches": [
                    {"key": "K1", "bgg_id": 100, "confidence": "high", "reasoning": "exact"},
                    {"key": "K2", "bgg_id": None, "confidence": "high", "reasoning": "seminar"},
                ]
            }),
        })

    summary = run(
        agent_input_path=agent_input,
        bgg_path=bgg,
        manual_path=manual_yaml,
        agent_path=agent_yaml,
        invoker=fake_invoker,
        batch_size=10,
    )

    assert summary.batches_run == 1
    assert summary.mappings_added == 2
    written = load_mapping(agent_yaml)
    assert written["K1"].bgg_id == 100
    assert written["K2"].bgg_id is None


def test_run_skips_already_mapped(tmp_path):
    agent_input = _agent_input(tmp_path)
    bgg = _bgg_csv(tmp_path)
    agent_yaml = tmp_path / "mappings.agent.yaml"
    manual_yaml = tmp_path / "mappings.yaml"
    # Pre-populate agent_yaml with K1
    agent_yaml.write_text("K1: 100\n")

    calls = []

    def fake_invoker(prompt: str) -> str:
        calls.append(prompt)
        return json.dumps({
            "type": "result",
            "result": json.dumps({
                "matches": [
                    {"key": "K2", "bgg_id": None, "confidence": "high", "reasoning": "seminar"},
                ]
            }),
        })

    summary = run(
        agent_input_path=agent_input, bgg_path=bgg,
        manual_path=manual_yaml, agent_path=agent_yaml,
        invoker=fake_invoker, batch_size=10,
    )
    assert "K1" not in calls[0]    # should not have been re-asked
    assert "K2" in calls[0]
    assert summary.mappings_added == 1


def test_run_retries_once_on_invalid_response(tmp_path):
    agent_input = _agent_input(tmp_path)
    bgg = _bgg_csv(tmp_path)
    agent_yaml = tmp_path / "mappings.agent.yaml"
    manual_yaml = tmp_path / "mappings.yaml"

    call_count = {"n": 0}
    def fake_invoker(prompt: str) -> str:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return json.dumps({"type": "result", "result": "garbage"})
        return json.dumps({
            "type": "result",
            "result": json.dumps({
                "matches": [
                    {"key": "K1", "bgg_id": 100, "confidence": "high", "reasoning": "ok"},
                    {"key": "K2", "bgg_id": None, "confidence": "low", "reasoning": "n/a"},
                ]
            }),
        })

    summary = run(
        agent_input_path=agent_input, bgg_path=bgg,
        manual_path=manual_yaml, agent_path=agent_yaml,
        invoker=fake_invoker, batch_size=10,
    )
    assert call_count["n"] == 2
    assert summary.mappings_added == 2
    assert summary.batches_rejected == 0


def test_run_skips_batch_after_two_failures(tmp_path):
    agent_input = _agent_input(tmp_path)
    bgg = _bgg_csv(tmp_path)
    agent_yaml = tmp_path / "mappings.agent.yaml"
    manual_yaml = tmp_path / "mappings.yaml"

    def fake_invoker(prompt: str) -> str:
        return json.dumps({"type": "result", "result": "garbage"})

    summary = run(
        agent_input_path=agent_input, bgg_path=bgg,
        manual_path=manual_yaml, agent_path=agent_yaml,
        invoker=fake_invoker, batch_size=10,
    )
    assert summary.batches_rejected == 1
    assert summary.mappings_added == 0


def test_dry_run_does_not_invoke(tmp_path):
    agent_input = _agent_input(tmp_path)
    bgg = _bgg_csv(tmp_path)
    agent_yaml = tmp_path / "mappings.agent.yaml"
    manual_yaml = tmp_path / "mappings.yaml"

    def fake_invoker(prompt: str) -> str:
        raise AssertionError("should not be called in dry-run mode")

    summary = run(
        agent_input_path=agent_input, bgg_path=bgg,
        manual_path=manual_yaml, agent_path=agent_yaml,
        invoker=fake_invoker, batch_size=10, dry_run=True,
    )
    assert summary.batches_run == 0
