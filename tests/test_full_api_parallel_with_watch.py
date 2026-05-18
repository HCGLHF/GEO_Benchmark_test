import argparse
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
    )

    config = prepare_config(args)

    assert config["performance"]["llm_cache"]["sqlite"] == str(tmp_path / "cache" / "openai.sqlite")
    assert config["performance"]["run_state"]["sqlite"] == str(tmp_path / "runs" / "model-a" / "run_state.sqlite")
    assert config["client_acquisition"]["queries_per_model"] == 7
    assert [model["model"] for model in config["models"]] == ["openai/gpt-4.1-mini"]


def test_parallel_with_watch_dry_run_prints_independent_runs_and_monitoring(tmp_path: Path):
    script = Path("scripts/run_full_api_parallel_with_watch.ps1")
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-QueriesPerModel",
            "3",
            "-RunRoot",
            str(tmp_path / "full_api_parallel"),
            "-DryRun",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout
    assert "scripts\\run_full_api_client_acquisition.py" in result.stdout
    assert "--cache-path" in result.stdout
    assert "scripts\\watch_full_api_run.py" in result.stdout
    assert "scripts\\merge_full_api_runs.py" in result.stdout
    assert "bytedance-seed/seed-2.0-pro" not in result.stdout
