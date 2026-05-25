import json
from pathlib import Path

from scripts.ops_logging import filter_events, read_events, write_event


def test_write_event_appends_stable_jsonl_record(tmp_path: Path) -> None:
    run_root = tmp_path / "run"

    event = write_event(
        run_root,
        level="warning",
        event_type="api_failure",
        stage="answer",
        model="openai/gpt-4.1-mini",
        message="Provider returned 429.",
        details={"query_id": "q001", "error": "429 Too Many Requests"},
        source="tests",
    )

    rows = (run_root / "ops_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    parsed = json.loads(rows[0])
    assert parsed["created_at"].endswith("Z")
    assert parsed["level"] == "warning"
    assert parsed["event_type"] == "api_failure"
    assert parsed["run_root"] == str(run_root)
    assert parsed["stage"] == "answer"
    assert parsed["model"] == "openai/gpt-4.1-mini"
    assert parsed["message"] == "Provider returned 429."
    assert parsed["details"] == {"query_id": "q001", "error": "429 Too Many Requests"}
    assert parsed["source"] == "tests"
    assert event == parsed


def test_filter_events_by_level_event_type_and_model(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    write_event(run_root, level="info", event_type="stage_started", model="", message="Started")
    write_event(run_root, level="error", event_type="worker_failed", model="model-a", message="Worker failed")
    write_event(run_root, level="error", event_type="api_failure", model="model-b", message="API failed")

    assert [event["event_type"] for event in filter_events(run_root, level="error")] == [
        "worker_failed",
        "api_failure",
    ]
    assert [event["model"] for event in filter_events(run_root, event_type="api_failure")] == ["model-b"]
    assert [event["event_type"] for event in filter_events(run_root, model="model-a")] == ["worker_failed"]


def test_read_events_skips_malformed_rows(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "ops_events.jsonl").write_text(
        '{"level":"info","event_type":"run_started"}\nnot-json\n{"level":"error","event_type":"worker_failed"}\n',
        encoding="utf-8",
    )

    assert [event["event_type"] for event in read_events(run_root)] == ["run_started", "worker_failed"]
