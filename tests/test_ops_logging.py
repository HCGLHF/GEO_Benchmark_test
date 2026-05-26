import json
from pathlib import Path

from scripts.pipeline_state import append_event, initialize_manifest
from scripts.ops_logging import filter_events, generate_summary, read_events, write_event, write_summary


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


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


def test_generate_summary_reports_ok_for_completed_pipeline_run(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    initialize_manifest(run_root=run_root, run_type="ui_pipeline", stages=["clean", "report"])
    append_event(run_root, stage="clean", status="completed", message="Cleaned")
    append_event(run_root, stage="report", status="completed", message="Report ready")

    summary = generate_summary(run_root)

    assert summary["status"] == "ok"
    assert summary["current_stage"] == ""
    assert summary["issues"] == []
    assert summary["recommended_actions"] == []
    assert summary["key_files"]["pipeline_state"] == "pipeline_state.jsonl"
    assert summary["key_files"]["ops_events"] == "ops_events.jsonl"


def test_generate_summary_reports_error_for_failed_worker_with_incomplete_outputs(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    model_dir = run_root / "openai_gpt-4.1-mini"
    model_dir.mkdir(parents=True)
    (model_dir / "run_config.resolved.json").write_text(
        json.dumps(
            {
                "models": [{"provider": "openrouter", "model": "openai/gpt-4.1-mini"}],
                "client_acquisition": {"queries_per_model": 1},
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "api_queries.csv").write_text("query_id,query\nq001,Need GEO\n", encoding="utf-8")
    (model_dir / "worker_exit_code.txt").write_text("1", encoding="utf-8")
    write_jsonl(
        model_dir / "api_orchestrator_attempts.jsonl",
        [
            {
                "task_type": "answer",
                "model": "openai/gpt-4.1-mini",
                "status": "error",
                "query_id": "q001",
                "error": "402 Payment Required",
            }
        ],
    )

    summary = generate_summary(run_root)

    assert summary["status"] == "error"
    assert any("openai_gpt-4.1-mini exited with code 1" in issue for issue in summary["issues"])
    assert any("Payment required" in action for action in summary["recommended_actions"])
    assert "openai_gpt-4.1-mini/worker.log" in summary["key_files"]["worker_logs"]


def test_generate_summary_reports_warning_for_rate_limit_with_complete_outputs(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    model_dir = run_root / "qwen_qwen3.7-max"
    model_dir.mkdir(parents=True)
    (model_dir / "run_config.resolved.json").write_text(
        json.dumps(
            {
                "models": [{"provider": "openrouter", "model": "qwen/qwen3.7-max"}],
                "client_acquisition": {"queries_per_model": 1},
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "api_queries.csv").write_text("query_id,query\nq001,Need GEO\n", encoding="utf-8")
    (model_dir / "retrieval_by_model.csv").write_text("query_id,model\nq001,qwen/qwen3.7-max\n", encoding="utf-8")
    (model_dir / "model_answer_evaluations.csv").write_text(
        "query_id,model,error\nq001,qwen/qwen3.7-max,\n",
        encoding="utf-8",
    )
    (model_dir / "worker_exit_code.txt").write_text("0", encoding="utf-8")
    write_jsonl(
        model_dir / "api_orchestrator_attempts.jsonl",
        [
            {"task_type": "rerank", "model": "qwen/qwen3.7-max", "status": "api_call"},
            {"task_type": "answer", "model": "qwen/qwen3.7-max", "status": "api_call"},
            {
                "task_type": "answer",
                "model": "qwen/qwen3.7-max",
                "status": "error",
                "query_id": "q001",
                "error": "429 Too Many Requests",
            },
        ],
    )

    summary = generate_summary(run_root)

    assert summary["status"] == "warning"
    assert any("rate-limit" in issue for issue in summary["issues"])
    assert any("backoff" in action.lower() for action in summary["recommended_actions"])


def test_generate_summary_reports_stalled_for_likely_stalled_incomplete_in_progress_run(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    model_dir = run_root / "qwen_qwen3.7-max"
    model_dir.mkdir(parents=True)
    (model_dir / "run_config.resolved.json").write_text(
        json.dumps(
            {
                "models": [{"provider": "openrouter", "model": "qwen/qwen3.7-max"}],
                "client_acquisition": {"queries_per_model": 1},
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "api_queries.csv").write_text("query_id,query\nq001,Need GEO\n", encoding="utf-8")
    write_jsonl(
        model_dir / "api_orchestrator_attempts.jsonl",
        [
            {
                "task_type": "rerank",
                "model": "qwen/qwen3.7-max",
                "status": "api_call",
                "query_id": "q001",
                "created_at": "2000-01-01T00:00:00Z",
            }
        ],
    )

    summary = generate_summary(run_root)

    assert summary["status"] == "stalled"
    assert any("likely_stalled" in issue for issue in summary["issues"])


def test_generate_summary_recommends_payment_action_for_hyphenated_payment_required_text(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    write_event(
        run_root,
        level="warning",
        event_type="api_failure",
        message="Provider returned payment-required.",
    )

    summary = generate_summary(run_root)

    assert any("Payment required" in action for action in summary["recommended_actions"])


def test_generate_summary_uses_api_call_summary_for_api_summary_key_file(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    model_dir = run_root / "qwen_qwen3.7-max"
    model_dir.mkdir(parents=True)
    (model_dir / "api_call_summary.csv").write_text("model,total_calls\nqwen/qwen3.7-max,1\n", encoding="utf-8")
    write_jsonl(
        model_dir / "api_orchestrator_attempts.jsonl",
        [{"task_type": "answer", "model": "qwen/qwen3.7-max", "status": "api_call"}],
    )

    summary = generate_summary(run_root)

    assert summary["key_files"]["api_summary"] == ["qwen_qwen3.7-max/api_call_summary.csv"]
    assert "qwen_qwen3.7-max/api_orchestrator_attempts.jsonl" not in summary["key_files"]["api_summary"]


def test_generate_summary_prefers_merged_api_call_summary_key_file(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    model_dir = run_root / "qwen_qwen3.7-max"
    model_dir.mkdir(parents=True)
    (run_root / "api_call_summary.csv").write_text("model,total_calls\nroot,1\n", encoding="utf-8")
    (run_root / "merged").mkdir()
    (run_root / "merged" / "api_call_summary.csv").write_text("model,total_calls\nmerged,2\n", encoding="utf-8")
    (model_dir / "api_call_summary.csv").write_text("model,total_calls\nmodel,1\n", encoding="utf-8")

    summary = generate_summary(run_root)

    assert summary["key_files"]["api_summary"] == ["merged/api_call_summary.csv"]


def test_generate_summary_uses_root_api_call_summary_when_merged_absent(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    model_dir = run_root / "qwen_qwen3.7-max"
    model_dir.mkdir(parents=True)
    (run_root / "api_call_summary.csv").write_text("model,total_calls\nroot,1\n", encoding="utf-8")
    (model_dir / "api_call_summary.csv").write_text("model,total_calls\nmodel,1\n", encoding="utf-8")

    summary = generate_summary(run_root)

    assert summary["key_files"]["api_summary"] == ["api_call_summary.csv"]


def test_generate_summary_keeps_active_incomplete_worker_without_failure_signal_ok(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    model_dir = run_root / "qwen_qwen3.7-max"
    model_dir.mkdir(parents=True)
    (model_dir / "run_config.resolved.json").write_text(
        json.dumps(
            {
                "models": [{"provider": "openrouter", "model": "qwen/qwen3.7-max"}],
                "client_acquisition": {"queries_per_model": 1},
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "api_queries.csv").write_text("query_id,query\nq001,Need GEO\n", encoding="utf-8")
    write_jsonl(
        model_dir / "api_orchestrator_attempts.jsonl",
        [{"task_type": "rerank", "model": "qwen/qwen3.7-max", "status": "api_call", "query_id": "q001"}],
    )

    summary = generate_summary(run_root)

    assert summary["status"] == "ok"


def test_write_summary_persists_summary_and_records_summary_event(tmp_path: Path) -> None:
    run_root = tmp_path / "run"

    summary = write_summary(run_root)

    assert (run_root / "ops_summary.json").exists()
    assert json.loads((run_root / "ops_summary.json").read_text(encoding="utf-8")) == summary
    assert any(event["event_type"] == "summary_generated" for event in read_events(run_root))
