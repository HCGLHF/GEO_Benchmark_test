from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_full_api_parallel_runner_dry_run_prints_expected_contract(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/full_api_parallel_runner.py",
            "--run-mode",
            "test",
            "--run-root",
            str(tmp_path / "full_api_parallel"),
            "--run-stamp",
            "fixed_stamp",
            "--models",
            "openai/gpt-4.1-mini",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "DRY RUN: full API parallel run with monitoring" in result.stdout
    assert f"Run root: {tmp_path / 'full_api_parallel' / 'fixed_stamp'}" in result.stdout
    assert "Run mode: test" in result.stdout
    assert "Queries per model: 2" in result.stdout
    assert "Selected models: openai/gpt-4.1-mini" in result.stdout
    assert "Progress HTML:" in result.stdout
    assert "Pipeline manifest:" in result.stdout
    assert "Pipeline state:" in result.stdout
    assert "Model: openai/gpt-4.1-mini" in result.stdout
    assert "scripts/run_full_api_client_acquisition.py" in result.stdout.replace("\\", "/")
    assert "--cache-path" in result.stdout
    assert "Watch: python scripts/watch_full_api_run.py --run-dir" in result.stdout.replace("\\", "/")
    assert "Merge:" in result.stdout
    assert "scripts/merge_full_api_runs.py" in result.stdout.replace("\\", "/")


def test_full_api_parallel_runner_quick_and_standard_query_defaults(tmp_path: Path) -> None:
    quick = subprocess.run(
        [
            sys.executable,
            "scripts/full_api_parallel_runner.py",
            "--run-mode",
            "quick",
            "--run-root",
            str(tmp_path / "quick"),
            "--run-stamp",
            "stamp",
            "--models",
            "openai/gpt-4.1-mini",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    standard = subprocess.run(
        [
            sys.executable,
            "scripts/full_api_parallel_runner.py",
            "--run-mode",
            "standard",
            "--run-root",
            str(tmp_path / "standard"),
            "--run-stamp",
            "stamp",
            "--models",
            "openai/gpt-4.1-mini",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert quick.returncode == 0, quick.stderr
    assert standard.returncode == 0, standard.stderr
    assert "Queries per model: 50" in quick.stdout
    assert "Queries per model: 200" in standard.stdout


def test_full_api_parallel_runner_rejects_empty_model_list(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/full_api_parallel_runner.py",
            "--run-root",
            str(tmp_path / "full_api_parallel"),
            "--models",
            "",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "No models selected" in result.stderr
