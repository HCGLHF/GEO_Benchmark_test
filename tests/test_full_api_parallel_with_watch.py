import argparse
import json
import subprocess
from pathlib import Path

from scripts.run_full_api_client_acquisition import prepare_config
from scripts.pipeline_state import read_pipeline_status


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
        ops_run_root=str(tmp_path / "runs" / "parallel"),
    )

    config = prepare_config(args)

    assert config["performance"]["llm_cache"]["sqlite"] == str(tmp_path / "cache" / "openai.sqlite")
    assert config["performance"]["run_state"]["sqlite"] == str(tmp_path / "runs" / "model-a" / "run_state.sqlite")
    assert config["run"]["ops_run_root"] == str(tmp_path / "runs" / "parallel")
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
    assert "'--queries-per-model' '50'" in result.stdout


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
    assert "'--queries-per-model' '2'" in result.stdout


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
    assert "'--queries-per-model' '200'" in result.stdout


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
    assert "'--queries-per-model' '9'" in result.stdout


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


def test_parallel_with_watch_counts_retargeted_seed_queries_for_changed_model_ids(tmp_path: Path):
    seed_dir = tmp_path / "seed_run"
    seed_dir.mkdir()
    (seed_dir / "api_queries.csv").write_text(
        "\n".join(
            [
                "query_id,provider,scenario_model,persona,stage,query",
                "q0001,openrouter,google/gemini-2.5-flash,owner,awareness,Need AI recommendations",
                "q0002,openrouter,google/gemini-2.5-flash,owner,awareness,Need GEO help",
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
            "-Models",
            "google/gemini-3.5-flash",
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

    assert "function Test-WorkerExitCodeReady" in script_text
    assert "function Read-WorkerExitCode" in script_text
    assert "Get-Content $ExitCodePath -TotalCount 1" in script_text
    assert "[string]::IsNullOrWhiteSpace($rawExitCode)" in script_text
    assert "Test-WorkerExitCodeReady -ExitCodePath" in script_text
    assert "Read-WorkerExitCode -ExitCodePath $exitCodePath -Process $worker.Process" in script_text


def test_parallel_with_watch_completes_seeded_scenario_stage_before_monitoring() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert '-Stage "scenario_generation" -Status "completed"' in script_text


def test_parallel_with_watch_serializes_manifest_metadata_with_json_converter() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert "ConvertTo-Json -Compress" in script_text
    assert "$metadataJson = $metadataJson.Replace('\"', '\\\"')" in script_text
    assert '"--metadata-json", $metadataJson' in script_text
    assert "Failed to initialize pipeline manifest" in script_text


def test_parallel_with_watch_allows_merge_with_model_warnings() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert "scripts\\full_api_run_status.py" in script_text
    assert "worker_exit_codes.json" in script_text
    assert "--exit-code-file" in script_text
    assert "complete_with_model_warnings" in script_text
    assert "Model workers completed with API warnings." in script_text
    assert "fatal_count" in script_text


def test_parallel_with_watch_writes_ops_events_and_summary() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert "function Write-OpsEvent" in script_text
    assert r"scripts\ops_logs.py" in script_text
    assert '"record"' in script_text
    assert '"run_started"' in script_text
    assert '"worker_failed"' in script_text
    assert '"run_completed"' in script_text
    assert '"doctor"' in script_text


def test_parallel_with_watch_passes_parent_ops_run_root_to_model_workers() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert '"--ops-run-root", $root' in script_text


def test_parallel_with_watch_worker_failed_ops_event_warns_on_cli_failure() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")
    worker_failed_index = script_text.index('"worker_failed"')
    worker_failed_branch = script_text[worker_failed_index : worker_failed_index + 800]

    assert "$LASTEXITCODE -ne 0" in worker_failed_branch
    assert 'Write-Warning "Could not write ops event worker_failed for ' in worker_failed_branch


def test_parallel_with_watch_avoids_string_evaluated_worker_and_merge_commands() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert "Invoke-Expression" not in script_text
    assert "$($worker.Command) *>&1" not in script_text
    assert "worker_python_args.json" in script_text
    assert "& python @pythonArgs" in script_text
    assert "& python @mergeArgs" in script_text


def test_parallel_with_watch_escapes_ops_details_json_for_native_python_calls() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert "function ConvertTo-NativeJsonArg" in script_text
    assert "$nativeDetailsJson = ConvertTo-NativeJsonArg -Json $DetailsJson" in script_text
    assert '"--details-json", $nativeDetailsJson' in script_text
    assert '$opsDetailsJson = "{`"exit_code`":$exitCode}"' in script_text
    assert "$nativeOpsDetailsJson = ConvertTo-NativeJsonArg -Json $opsDetailsJson" in script_text
    assert '"--details-json" $nativeOpsDetailsJson' in script_text


def test_parallel_with_watch_escapes_pipeline_details_json_for_native_python_calls() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert "$nativeDetailsJson = ConvertTo-NativeJsonArg -Json $DetailsJson" in script_text
    assert '"--details-json", $nativeDetailsJson' in script_text
    assert '$pipelineDetailsJson = "{`"exit_code`":$exitCode}"' in script_text
    assert "$nativePipelineDetailsJson = ConvertTo-NativeJsonArg -Json $pipelineDetailsJson" in script_text
    assert '"--details-json" $nativePipelineDetailsJson' in script_text
    assert '"--details-json" "{`"exit_code`":`$exitCode}"' not in script_text


def test_powershell_native_json_escaping_writes_valid_pipeline_details(tmp_path: Path) -> None:
    run_root = tmp_path / "pipeline-run"
    escaped_run_root = str(run_root).replace("'", "''")
    command = f"""
$runRoot = '{escaped_run_root}'
function ConvertTo-NativeJsonArg {{
  param([string]$Json)
  return $Json.Replace('"', '\\"')
}}
$mergeExitCode = 7
$mergeDetailsJson = '{{"exit_code":7}}'
$nativeMergeDetailsJson = ConvertTo-NativeJsonArg -Json $mergeDetailsJson
python "scripts\\pipeline_state.py" "append" "--run-root" $runRoot "--stage" "merge" "--status" "failed" "--message" "Merge failed." "--details-json" $nativeMergeDetailsJson | Out-Null
if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}
$exitCode = 9
$pipelineDetailsJson = "{{`"exit_code`":$exitCode}}"
$nativePipelineDetailsJson = $pipelineDetailsJson.Replace('"', '\\"')
python "scripts\\pipeline_state.py" "append" "--run-root" $runRoot "--stage" "answer" "--status" "failed" "--model" "model-a" "--message" "Worker failed." "--details-json" $nativePipelineDetailsJson | Out-Null
if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    status = read_pipeline_status(run_root)
    assert status["stages"]["merge"]["details"]["exit_code"] == 7
    assert status["stages"]["answer"]["details"]["exit_code"] == 9


def test_powershell_native_json_escaping_writes_valid_ops_details(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    escaped_run_root = str(run_root).replace("'", "''")
    command = f"""
$runRoot = '{escaped_run_root}'
function ConvertTo-NativeJsonArg {{
  param([string]$Json)
  return $Json.Replace('"', '\\"')
}}
$runDetailsJson = '{{"run_mode":"quick","queries_per_model":50}}'
$nativeRunDetailsJson = ConvertTo-NativeJsonArg -Json $runDetailsJson
python "scripts\\ops_logs.py" "record" "--run-root" $runRoot "--level" "info" "--event-type" "run_started" "--message" "Started." "--details-json" $nativeRunDetailsJson "--source" "test" | Out-Null
if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}
$exitCode = 7
$opsDetailsJson = "{{`"exit_code`":$exitCode}}"
$nativeOpsDetailsJson = $opsDetailsJson.Replace('"', '\\"')
python "scripts\\ops_logs.py" "record" "--run-root" $runRoot "--level" "error" "--event-type" "worker_failed" "--stage" "answer" "--model" "model-a" "--message" "Worker failed." "--details-json" $nativeOpsDetailsJson "--source" "test" | Out-Null
if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    events = [
        json.loads(line)
        for line in (run_root / "ops_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["event_type"] == "run_started"
    assert events[0]["details"] == {"run_mode": "quick", "queries_per_model": 50}
    assert events[1]["event_type"] == "worker_failed"
    assert events[1]["details"] == {"exit_code": 7}


def test_parallel_with_watch_handles_merge_command_failure_before_success_events() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")
    merge_index = script_text.index("& python @mergeArgs")
    report_completed_index = script_text.index(
        'Write-PipelineEvent -RunRootPath $root -Stage "report" -Status "completed"',
        merge_index,
    )
    merge_failure_branch = script_text[merge_index:report_completed_index]

    assert "$mergeExitCode = $LASTEXITCODE" in merge_failure_branch
    assert '-Stage "merge" -Status "failed"' in merge_failure_branch
    assert '-EventType "stage_failed" -Stage "merge"' in merge_failure_branch
    assert "Write-OpsSummary -RunRootPath $root" in merge_failure_branch
    assert "exit $mergeExitCode" in merge_failure_branch
