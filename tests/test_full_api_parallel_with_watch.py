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
    assert "Progress HTML:" in result.stdout
    assert "scripts\\merge_full_api_runs.py" in result.stdout
    assert "bytedance-seed/seed-2.0-pro" not in result.stdout


def test_parallel_with_watch_quick_mode_uses_about_100_seeded_calls_per_model(tmp_path: Path):
    script = Path("scripts/run_full_api_parallel_with_watch.ps1")
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-RunMode",
            "quick",
            "-RunRoot",
            str(tmp_path / "full_api_parallel"),
            "-DryRun",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Run mode: quick" in result.stdout
    assert "Queries per model: 50" in result.stdout
    assert "--queries-per-model\" \"50" in result.stdout


def test_parallel_with_watch_test_mode_uses_low_call_chain_check(tmp_path: Path):
    script = Path("scripts/run_full_api_parallel_with_watch.ps1")
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-RunMode",
            "test",
            "-RunRoot",
            str(tmp_path / "full_api_parallel"),
            "-DryRun",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Run mode: test" in result.stdout
    assert "Queries per model: 2" in result.stdout
    assert "--queries-per-model\" \"2" in result.stdout


def test_parallel_with_watch_standard_mode_keeps_400_seeded_calls_per_model(tmp_path: Path):
    script = Path("scripts/run_full_api_parallel_with_watch.ps1")
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-RunMode",
            "standard",
            "-RunRoot",
            str(tmp_path / "full_api_parallel"),
            "-DryRun",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Run mode: standard" in result.stdout
    assert "Queries per model: 200" in result.stdout
    assert "--queries-per-model\" \"200" in result.stdout


def test_parallel_with_watch_manual_query_count_overrides_run_mode(tmp_path: Path):
    script = Path("scripts/run_full_api_parallel_with_watch.ps1")
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-RunMode",
            "quick",
            "-QueriesPerModel",
            "9",
            "-RunRoot",
            str(tmp_path / "full_api_parallel"),
            "-DryRun",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Run mode: quick" in result.stdout
    assert "Queries per model: 9" in result.stdout
    assert "--queries-per-model\" \"9" in result.stdout


def test_parallel_with_watch_can_seed_existing_queries_per_model(tmp_path: Path):
    seed_dir = tmp_path / "seed_run"
    seed_dir.mkdir()
    (seed_dir / "api_queries.csv").write_text(
        "\n".join(
            [
                "query_id,provider,scenario_model,persona,stage,query",
                "q0001,openrouter,openai/gpt-4.1-mini,owner,awareness,Need AI recommendations",
                "q0002,openrouter,deepseek/deepseek-chat,owner,awareness,Need GEO help",
                "q0003,openrouter,google/gemini-2.5-flash,owner,awareness,Need AI visibility",
            ]
        ),
        encoding="utf-8",
    )
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
            "-SeedQueriesRunDir",
            str(seed_dir),
            "-DryRun",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Seed queries run: " in result.stdout
    assert "Seeded queries: 1" in result.stdout
    assert "Scenario generation will resume from seeded api_queries.csv" in result.stdout


def test_parallel_with_watch_limits_seeded_queries_to_queries_per_model(tmp_path: Path):
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
    script = Path("scripts/run_full_api_parallel_with_watch.ps1")

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-QueriesPerModel",
            "2",
            "-RunRoot",
            str(tmp_path / "full_api_parallel"),
            "-SeedQueriesRunDir",
            str(seed_dir),
            "-DryRun",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Seeded queries: 2" in result.stdout


def test_parallel_with_watch_runs_only_selected_model_subset(tmp_path: Path):
    script = Path("scripts/run_full_api_parallel_with_watch.ps1")

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-QueriesPerModel",
            "2",
            "-RunRoot",
            str(tmp_path / "full_api_parallel"),
            "-Models",
            "openai/gpt-4.1-mini,deepseek/deepseek-chat",
            "-DryRun",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Selected models: openai/gpt-4.1-mini, deepseek/deepseek-chat" in result.stdout
    assert "Pipeline manifest:" in result.stdout
    assert "Pipeline state:" in result.stdout
    assert "Model: openai/gpt-4.1-mini" in result.stdout
    assert "Model: deepseek/deepseek-chat" in result.stdout
    assert "Model: google/gemini-2.5-flash" not in result.stdout
    assert "Model: perplexity/sonar-pro" not in result.stdout


def test_parallel_with_watch_accepts_fixed_run_stamp(tmp_path: Path):
    script = Path("scripts/run_full_api_parallel_with_watch.ps1")
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-QueriesPerModel",
            "2",
            "-RunRoot",
            str(tmp_path / "full_api_parallel"),
            "-RunStamp",
            "fixed_stamp",
            "-Models",
            "openai/gpt-4.1-mini",
            "-DryRun",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert f"Run root: {tmp_path / 'full_api_parallel' / 'fixed_stamp'}" in result.stdout


def test_parallel_with_watch_waits_for_non_empty_worker_exit_code() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert "function Read-WorkerExitCode" in script_text
    assert "Get-Content $ExitCodePath -TotalCount 1" in script_text
    assert "[string]::IsNullOrWhiteSpace($rawExitCode)" in script_text
    assert "Read-WorkerExitCode -ExitCodePath $exitCodePath -Process $worker.Process" in script_text


def test_parallel_with_watch_completes_seeded_scenario_stage_before_monitoring() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert '-Stage "scenario_generation" -Status "completed"' in script_text
