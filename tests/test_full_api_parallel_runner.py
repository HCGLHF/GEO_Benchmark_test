from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.full_api_parallel_runner import (
    RunnerOptions,
    build_merge_args,
    build_run_root,
    build_worker_plans,
    parse_args,
    run,
)
from scripts.pipeline_state import read_pipeline_status
from scripts.platform_runtime import ProcessHandle, detect_platform


class FakeProcess:
    def __init__(self, returncode: int | None = 0):
        self.pid = 9000
        self.returncode = returncode

    def poll(self):
        return self.returncode


class FakeRuntime:
    platform_id = "wsl"
    path_style = "posix"
    python_executable = "python"

    def __init__(self, returncode: int = 0, call_order: list[str] | None = None):
        self.returncode = returncode
        self.call_order = call_order
        self.launched: list[list[str]] = []

    def path(self, value):
        return str(value).replace("\\", "/")

    def format_command(self, args):
        return " ".join(str(arg) for arg in args)

    def launch_worker(self, args, *, cwd, log_path):
        self.launched.append(list(args))
        output_dir = Path(args[args.index("--output-dir") + 1])
        model = args[args.index("--include-model") + 1]
        if self.call_order is not None:
            self.call_order.append(f"launch:{model}")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "run_config.resolved.json").write_text(
            json.dumps(
                {
                    "models": [{"provider": "openrouter", "model": model}],
                    "client_acquisition": {"queries_per_model": 1},
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "api_queries.csv").write_text("query_id,query\nq001,Need GEO\n", encoding="utf-8")
        (output_dir / "retrieval_by_model.csv").write_text(f"query_id,model\nq001,{model}\n", encoding="utf-8")
        (output_dir / "model_answer_evaluations.csv").write_text(
            f"query_id,model,error\nq001,{model},\n",
            encoding="utf-8",
        )
        (output_dir / "api_orchestrator_attempts.jsonl").write_text(
            json.dumps({"task_type": "rerank", "model": model, "status": "api_call"}) + "\n"
            + json.dumps({"task_type": "answer", "model": model, "status": "api_call"}) + "\n",
            encoding="utf-8",
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("fake worker complete\n", encoding="utf-8")
        return ProcessHandle(pid=9000, process_group_id=None, process=FakeProcess(self.returncode))


class StrictFakeRuntime(FakeRuntime):
    def launch_worker(self, args, *, cwd, log_path):
        self.launched.append(list(args))
        output_dir = Path(args[args.index("--output-dir") + 1])
        cache_path = Path(args[args.index("--cache-path") + 1])
        model = args[args.index("--include-model") + 1]
        with Path(log_path).open("a", encoding="utf-8") as log_handle:
            log_handle.write("strict fake worker complete\n")
        if not output_dir.exists():
            raise FileNotFoundError(f"missing output dir: {output_dir}")
        if not cache_path.parent.exists():
            raise FileNotFoundError(f"missing cache parent: {cache_path.parent}")
        (output_dir / "run_config.resolved.json").write_text(
            json.dumps(
                {
                    "models": [{"provider": "openrouter", "model": model}],
                    "client_acquisition": {"queries_per_model": 1},
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "api_queries.csv").write_text("query_id,query\nq001,Need GEO\n", encoding="utf-8")
        (output_dir / "retrieval_by_model.csv").write_text(f"query_id,model\nq001,{model}\n", encoding="utf-8")
        (output_dir / "model_answer_evaluations.csv").write_text(
            f"query_id,model,error\nq001,{model},\n",
            encoding="utf-8",
        )
        (output_dir / "api_orchestrator_attempts.jsonl").write_text(
            json.dumps({"task_type": "rerank", "model": model, "status": "api_call"}) + "\n"
            + json.dumps({"task_type": "answer", "model": model, "status": "api_call"}) + "\n",
            encoding="utf-8",
        )
        return ProcessHandle(pid=9000, process_group_id=None, process=FakeProcess(self.returncode))


class LaunchFailingRuntime(FakeRuntime):
    def __init__(self):
        super().__init__(returncode=None)
        self.stopped: list[int] = []

    def launch_worker(self, args, *, cwd, log_path):
        model = args[args.index("--include-model") + 1]
        if self.launched:
            raise RuntimeError(f"launch failed for {model}")
        self.launched.append(list(args))
        output_dir = Path(args[args.index("--output-dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("first worker launched\n", encoding="utf-8")
        return ProcessHandle(pid=9001, process_group_id=None, process=FakeProcess(None))

    def stop_process_tree(self, handle):
        self.stopped.append(handle.pid)


def fake_options(
    tmp_path: Path,
    *,
    models: list[str] | None = None,
    seed_queries_run_dir: str = "",
    skip_merge: bool = False,
) -> RunnerOptions:
    return RunnerOptions(
        config="config/client_acquisition_simulator.yaml",
        run_mode="test",
        queries_per_model=1,
        run_root=tmp_path / "full_api_parallel",
        run_stamp="fixed_stamp",
        monitor_interval_seconds=1,
        seed_queries_run_dir=seed_queries_run_dir,
        progress_html_path="",
        models=models or ["openai/gpt-4.1-mini"],
        include_doubao=False,
        skip_merge=skip_merge,
        sync_artifacts=False,
        corpus_version="2026-05-22-initial",
        industry="geo-agency",
        dry_run=False,
        platform="wsl",
    )


def write_seed_queries(seed_dir: Path, models: list[str]) -> None:
    seed_dir.mkdir()
    rows = ["query_id,provider,scenario_model,persona,stage,query"]
    for index, model in enumerate(models, start=1):
        rows.append(f"q{index:04d},openrouter,{model},owner,awareness,Need GEO")
    (seed_dir / "api_queries.csv").write_text("\n".join(rows), encoding="utf-8")


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


def test_full_api_parallel_runner_parses_sync_artifact_options(tmp_path: Path) -> None:
    options = parse_args(
        [
            "--run-root",
            str(tmp_path / "full_api_parallel"),
            "--models",
            "openai/gpt-4.1-mini",
            "--sync-artifacts",
            "--industry",
            "geo-agency",
            "--corpus-version",
            "2026-05-22-initial",
            "--dry-run",
        ]
    )

    assert options.sync_artifacts is True
    assert options.industry == "geo-agency"
    assert options.corpus_version == "2026-05-22-initial"


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


def test_full_api_parallel_runner_rejects_non_positive_monitor_interval() -> None:
    for value in ["0", "-1"]:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/full_api_parallel_runner.py",
                "--monitor-interval-seconds",
                value,
                "--models",
                "openai/gpt-4.1-mini",
                "--dry-run",
            ],
            check=False,
            text=True,
            capture_output=True,
        )

        assert result.returncode != 0
        assert "positive integer" in result.stderr


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


def test_full_api_parallel_runner_fake_execution_writes_run_contracts(tmp_path: Path, monkeypatch) -> None:
    runtime = FakeRuntime()

    def fake_run(args, check=False, text=True, capture_output=False):
        class Result:
            returncode = 0
            stdout = json.dumps(
                {"status": "complete", "fatal_count": 0, "warning_count": 0, "fatals": [], "warnings": []}
            )
            stderr = ""

        joined = " ".join(str(arg) for arg in args)
        if "merge_full_api_runs.py" in joined:
            output_dir = Path(args[args.index("--output-dir") + 1])
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "competitive_gap_report.md").write_text("# Report\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr("scripts.full_api_parallel_runner.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.full_api_parallel_runner.time.sleep", lambda seconds: None)

    result = run(fake_options(tmp_path), runtime=runtime)

    run_root = tmp_path / "full_api_parallel" / "fixed_stamp"
    assert result == 0
    assert runtime.launched
    assert (run_root / "worker_exit_codes.json").exists()
    assert json.loads((run_root / "worker_exit_codes.json").read_text(encoding="utf-8")) == {
        "openai_gpt-4.1-mini": "0"
    }
    assert (run_root / "ops_summary.json").exists()
    assert (run_root / "merged" / "competitive_gap_report.md").exists()
    status = read_pipeline_status(run_root)
    assert status["manifest"]["run_type"] == "full_api_parallel"
    assert status["manifest"]["metadata"] == {"run_mode": "test", "queries_per_model": 1}
    assert status["stages"]["answer"]["status"] == "completed"
    assert status["stages"]["merge"]["status"] == "completed"
    assert status["stages"]["report"]["status"] == "completed"


def test_full_api_parallel_runner_syncs_artifacts_after_successful_merge(tmp_path: Path, monkeypatch) -> None:
    runtime = FakeRuntime()
    sync_calls: list[dict] = []

    def fake_run(args, check=False, text=True, capture_output=False):
        class Result:
            returncode = 0
            stdout = json.dumps(
                {"status": "complete", "fatal_count": 0, "warning_count": 0, "fatals": [], "warnings": []}
            )
            stderr = ""

        joined = " ".join(str(arg) for arg in args)
        if "merge_full_api_runs.py" in joined:
            output_dir = Path(args[args.index("--output-dir") + 1])
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "competitive_gap_report.md").write_text("# Report\n", encoding="utf-8")
            (output_dir / "brand_performance_by_model.csv").write_text("brand,query_count\nAlphaXXXX,1\n", encoding="utf-8")
            (output_dir / "merge_manifest.json").write_text(
                json.dumps({"result": {"query_rows": 1, "source_run_count": 1}}),
                encoding="utf-8",
            )
        return Result()

    def fake_sync(**kwargs):
        sync_calls.append(kwargs)
        return {"status": "synced", "summary": {"run_count": 1, "artifact_count": 3, "size_bytes": 100}}

    options = RunnerOptions(
        **{
            **fake_options(tmp_path).__dict__,
            "run_mode": "quick",
            "sync_artifacts": True,
            "industry": "geo-agency",
            "corpus_version": "2026-05-22-initial",
        }
    )
    monkeypatch.setattr("scripts.full_api_parallel_runner.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.full_api_parallel_runner.time.sleep", lambda seconds: None)
    monkeypatch.setattr("scripts.full_api_parallel_runner.run_sync", fake_sync)

    result = run(options, runtime=runtime)

    assert result == 0
    assert len(sync_calls) == 1
    assert sync_calls[0]["industry_id"] == "geo-agency"
    assert sync_calls[0]["corpus_version"] == "2026-05-22-initial"
    assert sync_calls[0]["run_roots"] == [tmp_path / "full_api_parallel" / options.run_stamp]
    assert sync_calls[0]["run_modes"] == {"quick"}
    assert sync_calls[0]["execute"] is True


def test_full_api_parallel_runner_creates_worker_and_cache_dirs_before_no_seed_launch(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = StrictFakeRuntime()

    def fake_run(args, check=False, text=True, capture_output=False):
        class Result:
            returncode = 0
            stdout = json.dumps(
                {"status": "complete", "fatal_count": 0, "warning_count": 0, "fatals": [], "warnings": []}
            )
            stderr = ""

        joined = " ".join(str(arg) for arg in args)
        if "merge_full_api_runs.py" in joined:
            output_dir = Path(args[args.index("--output-dir") + 1])
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "competitive_gap_report.md").write_text("# Report\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr("scripts.full_api_parallel_runner.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.full_api_parallel_runner.time.sleep", lambda seconds: None)

    result = run(fake_options(tmp_path), runtime=runtime)

    run_root = tmp_path / "full_api_parallel" / "fixed_stamp"
    assert result == 0
    assert (run_root / "openai_gpt-4.1-mini").is_dir()
    assert (run_root / "cache").is_dir()


def test_full_api_parallel_runner_fatal_status_fails_before_merge(tmp_path: Path, monkeypatch) -> None:
    runtime = FakeRuntime()
    calls: list[str] = []

    def fake_run(args, check=False, text=True, capture_output=False):
        class Result:
            returncode = 0
            stdout = json.dumps(
                {
                    "status": "failed",
                    "fatal_count": 1,
                    "warning_count": 0,
                    "fatals": [{"safe_name": "openai_gpt-4.1-mini", "message": "missing answer rows"}],
                    "warnings": [],
                }
            )
            stderr = ""

        joined = " ".join(str(arg) for arg in args)
        calls.append(joined)
        return Result()

    monkeypatch.setattr("scripts.full_api_parallel_runner.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.full_api_parallel_runner.time.sleep", lambda seconds: None)

    result = run(fake_options(tmp_path), runtime=runtime)

    run_root = tmp_path / "full_api_parallel" / "fixed_stamp"
    assert result == 1
    assert (run_root / "ops_summary.json").exists()
    status = read_pipeline_status(run_root)
    assert status["stages"]["answer"]["status"] == "failed"
    assert not any("merge_full_api_runs.py" in call for call in calls)


def test_full_api_parallel_runner_stops_started_workers_when_later_launch_fails(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = LaunchFailingRuntime()

    def fake_run(args, check=False, text=True, capture_output=False):
        class Result:
            returncode = 0
            stdout = json.dumps(
                {"status": "failed", "fatal_count": 1, "warning_count": 0, "fatals": [], "warnings": []}
            )
            stderr = ""

        return Result()

    monkeypatch.setattr("scripts.full_api_parallel_runner.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.full_api_parallel_runner.time.sleep", lambda seconds: None)

    result = run(
        fake_options(tmp_path, models=["openai/gpt-4.1-mini", "qwen/qwen3.7-max"]),
        runtime=runtime,
    )

    run_root = tmp_path / "full_api_parallel" / "fixed_stamp"
    assert result == 1
    assert runtime.stopped == [9001]
    assert (run_root / "worker_exit_codes.json").exists()
    assert json.loads((run_root / "worker_exit_codes.json").read_text(encoding="utf-8")) == {
        "openai_gpt-4.1-mini": "1",
        "qwen_qwen3.7-max": "1",
    }
    assert (run_root / "ops_summary.json").exists()
    status = read_pipeline_status(run_root)
    assert status["stages"]["answer"]["status"] == "failed"


def test_full_api_parallel_runner_seeds_all_models_before_launching_workers(tmp_path: Path, monkeypatch) -> None:
    models = ["openai/gpt-4.1-mini", "qwen/qwen3.7-max"]
    seed_dir = tmp_path / "seed_run"
    write_seed_queries(seed_dir, models)
    call_order: list[str] = []
    runtime = FakeRuntime(call_order=call_order)

    def fake_run(args, check=False, text=True, capture_output=False):
        class Result:
            returncode = 0
            stdout = json.dumps(
                {"status": "complete", "fatal_count": 0, "warning_count": 0, "fatals": [], "warnings": []}
            )
            stderr = ""

        joined = " ".join(str(arg) for arg in args)
        if "seed_api_queries.py" in joined:
            call_order.append(f"seed:{args[args.index('--model') + 1]}")
        elif "merge_full_api_runs.py" in joined:
            output_dir = Path(args[args.index("--output-dir") + 1])
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "competitive_gap_report.md").write_text("# Report\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr("scripts.full_api_parallel_runner.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.full_api_parallel_runner.time.sleep", lambda seconds: None)

    result = run(
        fake_options(tmp_path, models=models, seed_queries_run_dir=str(seed_dir)),
        runtime=runtime,
    )

    assert result == 0
    assert call_order[:4] == [
        "seed:openai/gpt-4.1-mini",
        "seed:qwen/qwen3.7-max",
        "launch:openai/gpt-4.1-mini",
        "launch:qwen/qwen3.7-max",
    ]


def test_full_api_parallel_runner_seed_failure_preserves_exit_code_in_top_level_json(
    tmp_path: Path, monkeypatch
) -> None:
    model = "openai/gpt-4.1-mini"
    seed_dir = tmp_path / "seed_run"
    write_seed_queries(seed_dir, [model])
    runtime = FakeRuntime()

    def fake_run(args, check=False, text=True, capture_output=False):
        class Result:
            returncode = 0
            stdout = json.dumps(
                {
                    "status": "failed",
                    "fatal_count": 1,
                    "warning_count": 0,
                    "fatals": [{"safe_name": "openai_gpt-4.1-mini", "message": "seed failed"}],
                    "warnings": [],
                }
            )
            stderr = ""

        joined = " ".join(str(arg) for arg in args)
        if "seed_api_queries.py" in joined:
            Result.returncode = 7
            Result.stdout = ""
            Result.stderr = "seed failed"
        return Result()

    monkeypatch.setattr("scripts.full_api_parallel_runner.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.full_api_parallel_runner.time.sleep", lambda seconds: None)

    result = run(fake_options(tmp_path, seed_queries_run_dir=str(seed_dir)), runtime=runtime)

    run_root = tmp_path / "full_api_parallel" / "fixed_stamp"
    assert result == 7
    assert runtime.launched == []
    assert json.loads((run_root / "worker_exit_codes.json").read_text(encoding="utf-8")) == {
        "openai_gpt-4.1-mini": "7"
    }
