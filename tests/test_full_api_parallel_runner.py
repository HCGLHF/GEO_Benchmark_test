from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.full_api_parallel_runner import build_merge_args, build_run_root, build_worker_plans, parse_args
from scripts.platform_runtime import detect_platform


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


def test_full_api_parallel_runner_worker_plan_keeps_argv_safe_for_windows_and_wsl(tmp_path: Path) -> None:
    seed_dir = tmp_path / "seed dir & tricky"
    seed_dir.mkdir()
    (seed_dir / "api_queries.csv").write_text(
        "\n".join(
            [
                "query_id,provider,scenario_model,persona,stage,query",
                "q0001,openrouter,model with spaces & semi;colon,owner,awareness,Need help",
            ]
        ),
        encoding="utf-8",
    )
    options = parse_args(
        [
            "--config",
            str(tmp_path / "config & special.yaml"),
            "--run-root",
            str(tmp_path / "run root"),
            "--run-stamp",
            "stamp",
            "--models",
            "model with spaces & semi;colon",
            "--seed-queries-run-dir",
            str(seed_dir),
            "--dry-run",
        ]
    )
    run_root = build_run_root(options)

    for platform in ["windows", "wsl"]:
        runtime = detect_platform(platform)
        worker = build_worker_plans(options, runtime, run_root, ["model with spaces & semi;colon"])[0]
        merge_args = build_merge_args(options, runtime, [worker], run_root / "merged")

        assert isinstance(worker.python_args, list)
        assert isinstance(worker.watch_args, list)
        assert isinstance(worker.seed_args, list)
        assert worker.python_args[worker.python_args.index("--include-model") + 1] == "model with spaces & semi;colon"
        assert worker.python_args[worker.python_args.index("--config") + 1].endswith("config & special.yaml")
        assert worker.seed_args[worker.seed_args.index("--seed-run-dir") + 1].endswith("seed dir & tricky")
        assert worker.seed_args[worker.seed_args.index("--model") + 1] == "model with spaces & semi;colon"
        assert merge_args[merge_args.index("--runs") + 1] == runtime.path(worker.run_dir)
        assert "&" not in worker.python_args[0]
        assert ";" not in worker.python_args[0]


def test_full_api_parallel_runner_wsl_dry_run_prints_posix_paths_and_python3(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/full_api_parallel_runner.py",
            "--platform",
            "wsl",
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
    assert "\\" not in result.stdout
    assert f"Run root: {str(tmp_path / 'full_api_parallel' / 'fixed_stamp').replace('\\', '/')}" in result.stdout
    assert "Watch: python3 scripts/watch_full_api_run.py --run-dir" in result.stdout
    assert "python3 scripts/merge_full_api_runs.py" in result.stdout


def test_full_api_parallel_runner_seeded_dry_run_prints_seed_command(tmp_path: Path) -> None:
    seed_dir = tmp_path / "seed_run"
    seed_dir.mkdir()
    (seed_dir / "api_queries.csv").write_text(
        "\n".join(
            [
                "query_id,provider,scenario_model,persona,stage,query",
                "q0001,openrouter,openai/gpt-4.1-mini,owner,awareness,Need AI recommendations",
                "q0002,openrouter,openai/gpt-4.1-mini,owner,awareness,Need GEO help",
                "q0003,openrouter,deepseek/deepseek-chat,owner,awareness,Need other help",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/full_api_parallel_runner.py",
            "--run-root",
            str(tmp_path / "full_api_parallel"),
            "--run-stamp",
            "stamp",
            "--queries-per-model",
            "2",
            "--models",
            "openai/gpt-4.1-mini",
            "--seed-queries-run-dir",
            str(seed_dir),
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Seeded queries: 2" in result.stdout
    assert "Seed command:" in result.stdout
    assert "scripts/seed_api_queries.py" in result.stdout.replace("\\", "/")
    assert "--seed-run-dir" in result.stdout
    assert "--limit 2" in result.stdout
