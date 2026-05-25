import subprocess
import json
from pathlib import Path

from scripts.ops_logging import read_events
from scripts.pipeline_state import read_pipeline_status


def test_run_pipeline_step_records_successful_command(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    result = subprocess.run(
        [
            "python",
            "scripts/run_pipeline_step.py",
            "--run-root",
            str(run_root),
            "--stage",
            "clean",
            "--",
            "python",
            "-c",
            "print('clean ok')",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    status = read_pipeline_status(run_root)
    assert status["stages"]["clean"]["status"] == "completed"
    assert (run_root / "logs" / "clean.log").exists()


def test_run_pipeline_step_records_failed_command(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    result = subprocess.run(
        [
            "python",
            "scripts/run_pipeline_step.py",
            "--run-root",
            str(run_root),
            "--stage",
            "index",
            "--",
            "python",
            "-c",
            "raise SystemExit(7)",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 7
    status = read_pipeline_status(run_root)
    assert status["stages"]["index"]["status"] == "failed"
    assert status["stages"]["index"]["details"]["exit_code"] == 7


def test_run_pipeline_step_writes_ops_events_for_success(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    result = subprocess.run(
        [
            "python",
            "scripts/run_pipeline_step.py",
            "--run-root",
            str(run_root),
            "--stage",
            "clean",
            "--",
            "python",
            "-c",
            "print('clean ok')",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    events = read_events(run_root)
    assert [event["event_type"] for event in events] == ["stage_started", "stage_completed"]
    assert events[0]["level"] == "info"
    assert events[1]["details"]["exit_code"] == 0


def test_run_pipeline_step_writes_ops_event_for_failure(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    result = subprocess.run(
        [
            "python",
            "scripts/run_pipeline_step.py",
            "--run-root",
            str(run_root),
            "--stage",
            "index",
            "--",
            "python",
            "-c",
            "raise SystemExit(7)",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 7
    events = read_events(run_root)
    assert [event["event_type"] for event in events] == ["stage_started", "stage_failed"]
    assert events[1]["level"] == "error"
    assert events[1]["details"]["exit_code"] == 7


def test_run_pipeline_step_redacts_sensitive_command_values_from_run_logs(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    secret = "sk-secret-value"
    prompt_fragment = "PROMPT_FRAGMENT_DO_NOT_COPY"
    result = subprocess.run(
        [
            "python",
            "scripts/run_pipeline_step.py",
            "--run-root",
            str(run_root),
            "--stage",
            "clean",
            "--",
            "python",
            "-c",
            "print('clean ok')",
            "--api-key",
            secret,
            f"--prompt={prompt_fragment}",
            "--prompt-text",
            prompt_fragment,
            f"--messages-json={prompt_fragment}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    ops_text = (run_root / "ops_events.jsonl").read_text(encoding="utf-8")
    pipeline_text = (run_root / "pipeline_state.jsonl").read_text(encoding="utf-8")
    assert secret not in ops_text
    assert secret not in pipeline_text
    assert prompt_fragment not in ops_text
    assert prompt_fragment not in pipeline_text
    started_event = json.loads(ops_text.splitlines()[0])
    assert started_event["details"]["command"][started_event["details"]["command"].index("--api-key") + 1] == "[redacted]"
    assert "--prompt=[redacted]" in started_event["details"]["command"]
    assert started_event["details"]["command"][started_event["details"]["command"].index("--prompt-text") + 1] == "[redacted]"
    assert "--messages-json=[redacted]" in started_event["details"]["command"]
