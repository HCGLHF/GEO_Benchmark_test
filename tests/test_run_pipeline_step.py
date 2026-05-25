import subprocess
from pathlib import Path

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
