import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.watch_full_api_run import find_latest_run, format_text_report, summarize_run


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def make_sample_run(run_dir: Path) -> None:
    write_json(
        run_dir / "run_config.resolved.json",
        {
            "models": [{"provider": "openrouter", "model": "model-a"}],
            "client_acquisition": {
                "queries_per_model": 2,
                "personas": ["Founder"],
                "journey_stages": ["vendor_discovery"],
            },
        },
    )
    write_csv(
        run_dir / "api_queries.csv",
        [
            {"query_id": "q001", "scenario_model": "model-a"},
            {"query_id": "q002", "scenario_model": "model-a"},
        ],
        ["query_id", "scenario_model"],
    )
    write_csv(
        run_dir / "retrieval_by_model.csv",
        [{"query_id": "q001", "model": "model-a"}],
        ["query_id", "model"],
    )
    write_csv(
        run_dir / "model_answer_evaluations.csv",
        [{"query_id": "q001", "model": "model-a", "error": ""}],
        ["query_id", "model", "error"],
    )
    write_jsonl(
        run_dir / "api_orchestrator_attempts.jsonl",
        [
            {
                "task_type": "scenario_generation",
                "provider": "openrouter",
                "model": "model-a",
                "status": "api_call",
                "created_at": "2026-05-18T01:00:00Z",
            },
            {
                "task_type": "rerank",
                "provider": "openrouter",
                "model": "model-a",
                "status": "cache_hit",
                "created_at": "2026-05-18T01:01:00Z",
            },
            {
                "task_type": "rerank",
                "provider": "openrouter",
                "model": "model-a",
                "status": "error",
                "error": "rate limited",
                "created_at": "2026-05-18T01:02:00Z",
            },
            {
                "task_type": "answer",
                "provider": "openrouter",
                "model": "model-a",
                "status": "api_call",
                "created_at": "2026-05-18T01:03:00Z",
            },
        ],
    )


def test_summarize_run_counts_attempts_by_model_and_task(tmp_path: Path):
    run_dir = tmp_path / "run"
    make_sample_run(run_dir)

    summary = summarize_run(run_dir, now=datetime(2026, 5, 18, 1, 5, tzinfo=timezone.utc))

    assert summary["totals"]["queries"] == 2
    assert summary["totals"]["expected_api_calls"] == 5
    assert summary["totals"]["terminal_calls"] == 4
    assert summary["totals"]["failures"] == 1
    assert summary["missing"]["retrieval_rows"] == 1
    assert summary["missing"]["answer_rows"] == 1
    assert summary["missing"]["terminal_calls"] == 1
    assert summary["tasks"]["scenario_generation"]["api_calls"] == 1
    assert summary["tasks"]["rerank"]["cache_hits"] == 1
    assert summary["tasks"]["rerank"]["failures"] == 1
    assert summary["models"]["model-a"]["api_calls"] == 2
    assert summary["models"]["model-a"]["failures"] == 1
    assert summary["outputs"]["retrieval_rows"] == 1
    assert summary["status"] == "active"


def test_summarize_run_does_not_expect_scenario_calls_for_seeded_queries(tmp_path: Path):
    run_dir = tmp_path / "seeded_run"
    write_json(
        run_dir / "run_config.resolved.json",
        {
            "models": [{"provider": "openrouter", "model": "model-a"}],
            "client_acquisition": {
                "queries_per_model": 2,
                "personas": ["Founder"],
                "journey_stages": ["vendor_discovery"],
            },
        },
    )
    write_csv(
        run_dir / "api_queries.csv",
        [
            {"query_id": "q001", "scenario_model": "model-a"},
            {"query_id": "q002", "scenario_model": "model-a"},
        ],
        ["query_id", "scenario_model"],
    )
    write_jsonl(
        run_dir / "api_orchestrator_attempts.jsonl",
        [
            {
                "task_type": "rerank",
                "provider": "openrouter",
                "model": "model-a",
                "status": "api_call",
                "created_at": "2026-05-18T01:00:00Z",
            },
            {
                "task_type": "answer",
                "provider": "openrouter",
                "model": "model-a",
                "status": "api_call",
                "created_at": "2026-05-18T01:01:00Z",
            },
        ],
    )

    summary = summarize_run(run_dir, now=datetime(2026, 5, 18, 1, 2, tzinfo=timezone.utc))

    assert summary["expected_by_task"]["scenario_generation"] == 0
    assert summary["totals"]["expected_api_calls"] == 4
    assert summary["missing"]["terminal_calls"] == 2


def test_summarize_run_treats_completed_queries_per_model_smoke_as_complete(tmp_path: Path):
    run_dir = tmp_path / "smoke_run"
    write_json(
        run_dir / "run_config.resolved.json",
        {
            "models": [{"provider": "openrouter", "model": "model-a"}],
            "client_acquisition": {
                "queries_per_model": 1,
                "queries_per_stage": 1,
                "personas": ["Founder", "Agency", "Local"],
                "journey_stages": [
                    "problem_aware",
                    "solution_aware",
                    "vendor_discovery",
                    "trust_validation",
                    "objection_handling",
                ],
            },
        },
    )
    write_csv(
        run_dir / "api_queries.csv",
        [{"query_id": "q001", "scenario_model": "model-a"}],
        ["query_id", "scenario_model"],
    )
    write_csv(
        run_dir / "retrieval_by_model.csv",
        [{"query_id": "q001", "model": "model-a"}],
        ["query_id", "model"],
    )
    write_csv(
        run_dir / "model_answer_evaluations.csv",
        [{"query_id": "q001", "model": "model-a", "error": ""}],
        ["query_id", "model", "error"],
    )
    write_jsonl(
        run_dir / "api_orchestrator_attempts.jsonl",
        [
            {
                "task_type": "scenario_generation",
                "provider": "openrouter",
                "model": "model-a",
                "status": "api_call",
                "created_at": "2026-05-18T01:00:00Z",
            },
            {
                "task_type": "rerank",
                "provider": "openrouter",
                "model": "model-a",
                "status": "api_call",
                "created_at": "2026-05-18T01:01:00Z",
            },
            {
                "task_type": "answer",
                "provider": "openrouter",
                "model": "model-a",
                "status": "api_call",
                "created_at": "2026-05-18T01:02:00Z",
            },
        ],
    )

    summary = summarize_run(run_dir, now=datetime(2026, 5, 18, 2, 0, tzinfo=timezone.utc))

    assert summary["status"] == "complete"
    assert summary["expected_by_task"]["scenario_generation"] == 1
    assert summary["missing"]["terminal_calls"] == 0


def test_summarize_run_handles_missing_files(tmp_path: Path):
    run_dir = tmp_path / "empty_run"
    run_dir.mkdir()

    summary = summarize_run(run_dir)

    assert summary["status"] == "empty"
    assert summary["totals"]["queries"] == 0
    assert summary["tasks"] == {}
    assert summary["warnings"]


def test_summarize_run_marks_idle_attempts_as_likely_stalled(tmp_path: Path):
    run_dir = tmp_path / "run"
    make_sample_run(run_dir)

    summary = summarize_run(
        run_dir,
        now=datetime(2026, 5, 18, 2, 0, tzinfo=timezone.utc),
        stall_after_seconds=900,
    )

    assert summary["status"] == "likely_stalled"
    assert summary["timing"]["idle_seconds"] == 3420


def test_format_text_report_includes_progress_and_failures(tmp_path: Path):
    run_dir = tmp_path / "run"
    make_sample_run(run_dir)
    summary = summarize_run(run_dir, now=datetime(2026, 5, 18, 1, 5, tzinfo=timezone.utc))

    report = format_text_report(summary)

    assert "Run:" in report
    assert "Progress: 4/5 terminal calls (80.0%)" in report
    assert "Missing: retrieval 1, answers 1, terminal calls 1" in report
    assert "model-a" in report
    assert "Failures:" in report
    assert "rate limited" in report


def test_find_latest_run_uses_most_recent_matching_directory(tmp_path: Path):
    older = tmp_path / "client_acquisition_simulator_full_api_20260518_010000"
    newer = tmp_path / "client_acquisition_simulator_full_api_20260518_020000"
    older.mkdir()
    newer.mkdir()

    assert find_latest_run(tmp_path) == newer
