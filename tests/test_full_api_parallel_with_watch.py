import argparse
import os
import shutil
import subprocess
from pathlib import Path

from scripts.run_full_api_client_acquisition import prepare_config


def write_minimal_config(path: Path) -> None:
    path.write_text(
        """
run:
  output_dir: runs/default
performance:
  llm_cache:
    enabled: true
    sqlite: data/cache/llm_calls.sqlite
models:
  - provider: openrouter
    model: openai/gpt-4.1-mini
  - provider: openrouter
    model: deepseek/deepseek-chat
client_acquisition:
  queries_per_model: 200
""".strip(),
        encoding="utf-8",
    )


def run_powershell_wrapper(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts/run_full_api_parallel_with_watch.ps1",
            *args,
        ],
        check=False,
        text=True,
        capture_output=True,
    )


def test_prepare_config_allows_cache_path_override(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    write_minimal_config(config_path)
    args = argparse.Namespace(
        config=str(config_path),
        output_dir=str(tmp_path / "runs" / "model-a"),
        queries_per_model=7,
        include_model=["openai/gpt-4.1-mini"],
        exclude_model=[],
        cache_path=str(tmp_path / "cache" / "openai.sqlite"),
        ops_run_root=str(tmp_path / "runs" / "parallel"),
    )

    config = prepare_config(args)

    assert config["performance"]["llm_cache"]["sqlite"] == str(tmp_path / "cache" / "openai.sqlite")
    assert config["performance"]["run_state"]["sqlite"] == str(tmp_path / "runs" / "model-a" / "run_state.sqlite")
    assert config["run"]["ops_run_root"] == str(tmp_path / "runs" / "parallel")
    assert config["client_acquisition"]["queries_per_model"] == 7
    assert [model["model"] for model in config["models"]] == ["openai/gpt-4.1-mini"]


def test_powershell_wrapper_dry_run_uses_python_runner_contract(tmp_path: Path) -> None:
    result = run_powershell_wrapper(
        "-RunMode",
        "test",
        "-RunRoot",
        str(tmp_path / "full_api_parallel"),
        "-RunStamp",
        "fixed_stamp",
        "-Models",
        "openai/gpt-4.1-mini,deepseek/deepseek-chat",
        "-ProgressHtmlPath",
        str(tmp_path / "progress.html"),
        "-DryRun",
    )

    assert result.returncode == 0, result.stderr
    stdout = result.stdout.replace("\\", "/")
    assert "DRY RUN: full API parallel run with monitoring" in stdout
    assert f"Run root: {str(tmp_path / 'full_api_parallel' / 'fixed_stamp').replace('\\', '/')}" in stdout
    assert "Run mode: test" in stdout
    assert "Queries per model: 2" in stdout
    assert "Selected models: openai/gpt-4.1-mini, deepseek/deepseek-chat" in stdout
    assert f"Progress HTML: {str(tmp_path / 'progress.html').replace('\\', '/')}" in stdout
    assert "Model: openai/gpt-4.1-mini" in stdout
    assert "Model: deepseek/deepseek-chat" in stdout
    assert "scripts/run_full_api_client_acquisition.py" in stdout
    assert "Watch: python scripts/watch_full_api_run.py --run-dir" in stdout
    assert "Merge:" in stdout
    assert "scripts/merge_full_api_runs.py" in stdout


def test_powershell_wrapper_forwards_manual_query_count_seed_skip_merge_and_stamp(tmp_path: Path) -> None:
    seed_dir = tmp_path / "seed_run"
    seed_dir.mkdir()
    (seed_dir / "api_queries.csv").write_text(
        "\n".join(
            [
                "query_id,provider,scenario_model,persona,stage,query",
                "q0001,openrouter,openai/gpt-4.1-mini,owner,awareness,Need AI recommendations",
                "q0002,openrouter,openai/gpt-4.1-mini,owner,awareness,Need GEO help",
                "q0003,openrouter,openai/gpt-4.1-mini,owner,awareness,Need AI visibility",
            ]
        ),
        encoding="utf-8",
    )

    result = run_powershell_wrapper(
        "-RunMode",
        "standard",
        "-QueriesPerModel",
        "2",
        "-RunRoot",
        str(tmp_path / "parallel"),
        "-RunStamp",
        "fixed",
        "-SelectedModels",
        "openai/gpt-4.1-mini",
        "-SeedQueriesRunDir",
        str(seed_dir),
        "-SkipMerge",
        "-DryRun",
    )

    assert result.returncode == 0, result.stderr
    stdout = result.stdout.replace("\\", "/")
    assert f"Run root: {str(tmp_path / 'parallel' / 'fixed').replace('\\', '/')}" in stdout
    assert "Run mode: standard" in stdout
    assert "Queries per model: 2" in stdout
    assert f"Seed queries run: {str(seed_dir).replace('\\', '/')}" in stdout
    assert "Seeded queries: 2" in stdout
    assert "Seed command:" in stdout
    assert "scripts/seed_api_queries.py" in stdout
    assert "Skip merge set. Merge command:" in stdout


def test_powershell_wrapper_is_thin() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert "scripts\\full_api_parallel_runner.py" in script_text
    assert "& python @runnerArgs" in script_text
    assert "exit $LASTEXITCODE" in script_text
    for removed_orchestration in [
        "Write-PipelineInit",
        "Write-OpsEvent",
        "Start-Process",
        "worker_launcher.ps1",
        "Invoke-Expression",
        "scripts\\run_full_api_client_acquisition.py",
        "scripts\\merge_full_api_runs.py",
        "scripts\\seed_api_queries.py",
    ]:
        assert removed_orchestration not in script_text


def test_bash_wrapper_forwards_to_python_runner_with_posix_paths(tmp_path: Path) -> None:
    script = Path("scripts/run_full_api_parallel_with_watch.sh")
    assert script.exists()
    script_text = script.read_text(encoding="utf-8")
    assert script_text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in script_text
    assert 'exec python scripts/full_api_parallel_runner.py "$@"' in script_text

    git_bash_dir = Path("C:/Program Files/Git/bin")
    env = os.environ.copy()
    bash_command = "bash"
    if shutil.which("bash") is None and (git_bash_dir / "bash.exe").exists():
        existing_path = env.get("PATH") or env.get("Path") or ""
        env["PATH"] = f"{git_bash_dir}{os.pathsep}{existing_path}"
        env["Path"] = env["PATH"]
        bash_command = str(git_bash_dir / "bash.exe")

    result = subprocess.run(
        [
            bash_command,
            str(script),
            "--platform",
            "wsl",
            "--run-mode",
            "test",
            "--run-root",
            str(tmp_path / "parallel"),
            "--run-stamp",
            "fixed",
            "--models",
            "openai/gpt-4.1-mini",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert "\\" not in result.stdout
    assert f"Run root: {str(tmp_path / 'parallel' / 'fixed').replace('\\', '/')}" in result.stdout
    assert "Run mode: test" in result.stdout
    assert "Selected models: openai/gpt-4.1-mini" in result.stdout
    assert "python3 scripts/run_full_api_client_acquisition.py" in result.stdout
    assert "scripts/full_api_parallel_runner.py" in script_text
