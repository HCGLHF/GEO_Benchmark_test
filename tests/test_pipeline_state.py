from pathlib import Path

from scripts.pipeline_state import append_event, initialize_manifest, read_pipeline_status


def test_pipeline_state_records_manifest_events_and_current_stage(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "sample"

    initialize_manifest(
        run_root=run_root,
        run_type="full_api_parallel",
        stages=["crawl", "clean", "chunk", "index", "AWS sync", "rerank", "answer", "merge", "report"],
        models=["openai/gpt-4.1-mini", "deepseek/deepseek-chat"],
        metadata={"run_mode": "quick"},
    )
    append_event(run_root, stage="crawl", status="completed", message="Crawled owned site", details={"urls": 37})
    append_event(run_root, stage="rerank", status="running", message="Rerank workers active")

    status = read_pipeline_status(run_root)

    assert (run_root / "run_manifest.json").exists()
    assert (run_root / "pipeline_state.jsonl").exists()
    assert status["manifest"]["run_type"] == "full_api_parallel"
    assert status["manifest"]["models"] == ["openai/gpt-4.1-mini", "deepseek/deepseek-chat"]
    assert status["current_stage"] == "rerank"
    assert status["stages"]["crawl"]["status"] == "completed"
    assert status["stages"]["crawl"]["details"]["urls"] == 37
    assert status["stages"]["rerank"]["status"] == "running"
    assert len(status["events"]) == 2


def test_pipeline_state_ignores_stale_failed_event_after_stage_recovers(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "recovered"

    initialize_manifest(
        run_root=run_root,
        run_type="full_api_parallel",
        stages=["scenario_generation", "answer", "merge", "report"],
        models=[],
    )
    append_event(run_root, stage="scenario_generation", status="completed")
    append_event(run_root, stage="answer", status="failed")
    append_event(run_root, stage="answer", status="completed")
    append_event(run_root, stage="merge", status="completed")
    append_event(run_root, stage="report", status="completed")

    status = read_pipeline_status(run_root)

    assert status["stages"]["answer"]["status"] == "completed"
    assert status["current_stage"] == ""


def test_pipeline_state_completed_report_is_terminal_even_with_unrun_setup_stages(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "api_only"

    initialize_manifest(
        run_root=run_root,
        run_type="full_api_parallel",
        stages=["crawl", "clean", "scenario_generation", "answer", "merge", "report"],
        models=[],
    )
    append_event(run_root, stage="scenario_generation", status="completed")
    append_event(run_root, stage="answer", status="completed")
    append_event(run_root, stage="merge", status="completed")
    append_event(run_root, stage="report", status="completed")

    status = read_pipeline_status(run_root)

    assert status["stages"]["crawl"]["status"] == "pending"
    assert status["stages"]["report"]["status"] == "completed"
    assert status["current_stage"] == ""
