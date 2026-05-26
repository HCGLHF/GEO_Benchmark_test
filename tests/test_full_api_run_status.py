import csv
import json
import subprocess
import sys
from pathlib import Path

from scripts.full_api_run_status import summarize_run_dirs


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def make_complete_model_run(run_dir: Path, model: str, failures: list[dict] | None = None) -> None:
    (run_dir / "run_config.resolved.json").parent.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_config.resolved.json").write_text(
        json.dumps(
            {
                "models": [{"provider": "openrouter", "model": model}],
                "client_acquisition": {"queries_per_model": 1},
            }
        ),
        encoding="utf-8",
    )
    write_csv(run_dir / "api_queries.csv", [{"query_id": "q001", "query": "Need GEO"}], ["query_id", "query"])
    write_csv(run_dir / "retrieval_by_model.csv", [{"query_id": "q001", "model": model}], ["query_id", "model"])
    write_csv(
        run_dir / "model_answer_evaluations.csv",
        [{"query_id": "q001", "model": model, "error": ""}],
        ["query_id", "model", "error"],
    )
    attempts = [
        {"task_type": "rerank", "model": model, "status": "api_call", "query_id": "q001"},
        {"task_type": "answer", "model": model, "status": "api_call", "query_id": "q001"},
    ]
    attempts.extend(failures or [])
    write_jsonl(run_dir / "api_orchestrator_attempts.jsonl", attempts)


def test_summarize_run_dirs_marks_complete_rate_limit_failures_as_warnings(tmp_path: Path) -> None:
    qwen_run = tmp_path / "qwen_qwen3.7-max"
    make_complete_model_run(
        qwen_run,
        "qwen/qwen3.7-max",
        failures=[
            {
                "task_type": "rerank",
                "model": "qwen/qwen3.7-max",
                "status": "error",
                "query_id": "q001",
                "error": "OpenRouter 429 Too Many Requests",
            }
        ],
    )

    summary = summarize_run_dirs([qwen_run], {"qwen_qwen3.7-max": 0})

    assert summary["status"] == "complete_with_model_warnings"
    assert summary["fatal_count"] == 0
    assert summary["warning_count"] == 1
    assert summary["warnings"][0]["message"] == "Qwen had 1 rate-limit failure; interpret with caution."


def test_summarize_run_dirs_blocks_incomplete_failed_worker(tmp_path: Path) -> None:
    failed_run = tmp_path / "openai_gpt-4.1-mini"
    make_complete_model_run(failed_run, "openai/gpt-4.1-mini")
    (failed_run / "model_answer_evaluations.csv").write_text("query_id,model,error\n", encoding="utf-8")

    summary = summarize_run_dirs([failed_run], {"openai_gpt-4.1-mini": 1})

    assert summary["status"] == "failed"
    assert summary["fatal_count"] == 1
    assert "missing answer rows" in summary["fatals"][0]["message"]


def test_full_api_run_status_cli_reads_exit_code_file(tmp_path: Path) -> None:
    run_dir = tmp_path / "qwen_qwen3.7-max"
    make_complete_model_run(run_dir, "qwen/qwen3.7-max")
    exit_code_file = tmp_path / "exit_codes.json"
    exit_code_file.write_text(json.dumps({"qwen_qwen3.7-max": "0"}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/full_api_run_status.py",
            "--run-dir",
            str(run_dir),
            "--exit-code-file",
            str(exit_code_file),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "complete"
