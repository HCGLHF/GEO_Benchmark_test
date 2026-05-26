import json
import subprocess
from pathlib import Path

from scripts.ops_logging import write_event


def test_ops_logs_summary_generates_missing_summary(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    result = subprocess.run(
        ["python", "scripts/ops_logs.py", "summary", "--run-root", str(run_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert (run_root / "ops_summary.json").exists()


def test_ops_logs_events_filters_errors(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    write_event(run_root, level="info", event_type="run_started", message="Started")
    write_event(run_root, level="error", event_type="worker_failed", model="model-a", message="Failed")

    result = subprocess.run(
        ["python", "scripts/ops_logs.py", "events", "--run-root", str(run_root), "--level", "error"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert [row["event_type"] for row in rows] == ["worker_failed"]


def test_ops_logs_record_writes_event_for_powershell_runner(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    result = subprocess.run(
        [
            "python",
            "scripts/ops_logs.py",
            "record",
            "--run-root",
            str(run_root),
            "--level",
            "warning",
            "--event-type",
            "worker_failed",
            "--stage",
            "answer",
            "--model",
            "model-a",
            "--message",
            "Worker failed.",
            "--details-json",
            '{"exit_code":1}',
            "--source",
            "test",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    event = json.loads(result.stdout)
    assert event["event_type"] == "worker_failed"
    assert event["details"] == {"exit_code": 1}


def test_ops_logs_record_rejects_malformed_details_json_cleanly(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    result = subprocess.run(
        [
            "python",
            "scripts/ops_logs.py",
            "record",
            "--run-root",
            str(run_root),
            "--event-type",
            "worker_failed",
            "--details-json",
            '{"exit_code":',
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert "error:" in result.stderr
    assert "--details-json" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (run_root / "ops_events.jsonl").exists()


def test_ops_logs_record_rejects_non_object_details_json_cleanly(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    result = subprocess.run(
        [
            "python",
            "scripts/ops_logs.py",
            "record",
            "--run-root",
            str(run_root),
            "--event-type",
            "worker_failed",
            "--details-json",
            "[1, 2, 3]",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert "error:" in result.stderr
    assert "--details-json" in result.stderr
    assert "JSON object" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (run_root / "ops_events.jsonl").exists()


def test_ops_logs_doctor_prints_human_summary(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    write_event(run_root, level="warning", event_type="api_failure", message="429 Too Many Requests")

    result = subprocess.run(
        ["python", "scripts/ops_logs.py", "doctor", "--run-root", str(run_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "status: warning" in result.stdout
    assert "429 Too Many Requests" in result.stdout
    issues_start = result.stdout.index("issues:")
    actions_start = result.stdout.index("recommended_actions:")
    key_files_start = result.stdout.index("key_files:")
    issues_section = result.stdout[issues_start:actions_start]
    actions_section = result.stdout[actions_start:key_files_start]
    assert "Rate limit detected" not in issues_section
    assert "Rate limit detected" in actions_section


def test_ops_logs_doctor_returns_zero_for_operational_error_status(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    write_event(run_root, level="error", event_type="worker_failed", message="Worker failed.")

    result = subprocess.run(
        ["python", "scripts/ops_logs.py", "doctor", "--run-root", str(run_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "status: error" in result.stdout
