from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ops_logging import write_event, write_summary
from scripts.pipeline_state import append_event, initialize_manifest, update_manifest
from scripts.platform_runtime import PlatformRuntime, detect_platform


DEFAULT_MODELS = [
    "openai/gpt-4.1-mini",
    "google/gemini-3.5-flash",
    "perplexity/sonar-pro",
    "deepseek/deepseek-v4-flash",
    "qwen/qwen3.7-max",
    "x-ai/grok-build-0.1",
]
DOUBAO_MODEL = "bytedance-seed/seed-2.0-pro"
QUERY_DEFAULTS = {"test": 2, "quick": 50, "standard": 200}
PIPELINE_STAGES = [
    "crawl",
    "clean",
    "chunk",
    "index",
    "AWS sync",
    "scenario_generation",
    "rerank",
    "answer",
    "merge",
    "report",
]
OPS_SOURCE = "scripts/full_api_parallel_runner.py"


@dataclass(frozen=True)
class RunnerOptions:
    config: str
    run_mode: str
    queries_per_model: int
    run_root: Path
    run_stamp: str
    monitor_interval_seconds: int
    seed_queries_run_dir: str
    progress_html_path: str
    models: list[str]
    include_doubao: bool
    skip_merge: bool
    dry_run: bool
    platform: str


@dataclass(frozen=True)
class WorkerPlan:
    model: str
    safe_name: str
    run_dir: Path
    cache_path: Path
    python_args: list[str]
    watch_args: list[str]
    seed_args: list[str] | None
    seeded_query_count: int = 0


def parse_args(argv: list[str] | None = None) -> RunnerOptions:
    parser = argparse.ArgumentParser(description="Run full API client acquisition models in parallel.")
    parser.add_argument("--config", default="config/client_acquisition_simulator.yaml")
    parser.add_argument("--run-mode", choices=["test", "quick", "standard"], default="quick")
    parser.add_argument("--queries-per-model", type=int)
    parser.add_argument("--run-root", default="runs/full_api_parallel")
    parser.add_argument("--run-stamp", default="")
    parser.add_argument("--monitor-interval-seconds", type=int, default=30)
    parser.add_argument("--seed-queries-run-dir", default="")
    parser.add_argument("--progress-html-path", default="")
    parser.add_argument("--models", action="append", default=[])
    parser.add_argument("--include-doubao", action="store_true")
    parser.add_argument("--skip-merge", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--platform", choices=["auto", "windows", "linux", "wsl"], default="auto")
    args = parser.parse_args(argv)

    queries_per_model = args.queries_per_model
    if queries_per_model is None:
        queries_per_model = QUERY_DEFAULTS[args.run_mode]

    return RunnerOptions(
        config=args.config,
        run_mode=args.run_mode,
        queries_per_model=queries_per_model,
        run_root=Path(args.run_root),
        run_stamp=args.run_stamp,
        monitor_interval_seconds=args.monitor_interval_seconds,
        seed_queries_run_dir=args.seed_queries_run_dir,
        progress_html_path=args.progress_html_path,
        models=args.models,
        include_doubao=args.include_doubao,
        skip_merge=args.skip_merge,
        dry_run=args.dry_run,
        platform=args.platform,
    )


def selected_models(options: RunnerOptions) -> list[str]:
    models = list(DEFAULT_MODELS)
    if options.include_doubao:
        models.append(DOUBAO_MODEL)

    if options.models:
        parsed_models: list[str] = []
        seen: set[str] = set()
        for entry in options.models:
            for model in entry.split(","):
                model = model.strip()
                if model and model not in seen:
                    parsed_models.append(model)
                    seen.add(model)
        models = parsed_models

    if not models:
        raise ValueError("No models selected. Pass --models with at least one model id or use the defaults.")
    return models


def safe_name(value: str) -> str:
    return value.replace("/", "_").replace(":", "_")


def get_seed_queries(seed_run_dir: str, model: str, limit: int = 0) -> list[dict[str, str]]:
    if not seed_run_dir:
        return []

    seed_path = Path(seed_run_dir) / "api_queries.csv"
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed queries file not found: {seed_path}")

    with seed_path.open("r", encoding="utf-8-sig", newline="") as handle:
        all_rows = list(csv.DictReader(handle))

    rows = [row for row in all_rows if row.get("scenario_model") == model]
    if not rows and all_rows:
        counts = Counter(row.get("scenario_model", "") for row in all_rows)
        fallback_model = counts.most_common(1)[0][0]
        rows = [row for row in all_rows if row.get("scenario_model", "") == fallback_model]

    if limit > 0:
        rows = rows[:limit]
    if not rows:
        raise ValueError(f"No seeded queries found for model {model} in {seed_run_dir}")
    return rows


def build_run_root(options: RunnerOptions) -> Path:
    stamp = options.run_stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    return options.run_root / stamp


def build_worker_plans(
    options: RunnerOptions,
    runtime: PlatformRuntime,
    run_root: Path,
    models: list[str],
) -> list[WorkerPlan]:
    cache_root = run_root / "cache"
    workers: list[WorkerPlan] = []

    for model in models:
        model_safe_name = safe_name(model)
        run_dir = run_root / model_safe_name
        cache_path = cache_root / f"{model_safe_name}.sqlite"
        python_args = [
            runtime.python_executable,
            runtime.path("scripts/run_full_api_client_acquisition.py"),
            "--config",
            runtime.path(options.config),
            "--include-model",
            model,
            "--queries-per-model",
            str(options.queries_per_model),
            "--output-dir",
            runtime.path(run_dir),
            "--cache-path",
            runtime.path(cache_path),
            "--ops-run-root",
            runtime.path(run_root),
        ]
        watch_args = [
            runtime.python_executable,
            runtime.path("scripts/watch_full_api_run.py"),
            "--run-dir",
            runtime.path(run_dir),
        ]
        seed_args = None
        seeded_query_count = 0
        if options.seed_queries_run_dir:
            seeded_query_count = len(get_seed_queries(options.seed_queries_run_dir, model, options.queries_per_model))
            seed_args = [
                runtime.python_executable,
                runtime.path("scripts/seed_api_queries.py"),
                "--seed-run-dir",
                runtime.path(options.seed_queries_run_dir),
                "--model",
                model,
                "--output-dir",
                runtime.path(run_dir),
                "--limit",
                str(options.queries_per_model),
            ]

        workers.append(
            WorkerPlan(
                model=model,
                safe_name=model_safe_name,
                run_dir=run_dir,
                cache_path=cache_path,
                python_args=python_args,
                watch_args=watch_args,
                seed_args=seed_args,
                seeded_query_count=seeded_query_count,
            )
        )

    return workers


def build_merge_args(
    options: RunnerOptions,
    runtime: PlatformRuntime,
    workers: list[WorkerPlan],
    merged_dir: Path,
) -> list[str]:
    merge_args = [
        runtime.python_executable,
        runtime.path("scripts/merge_full_api_runs.py"),
        "--config",
        runtime.path(options.config),
        "--runs",
    ]
    merge_args.extend(runtime.path(worker.run_dir) for worker in workers)
    merge_args.extend(["--output-dir", runtime.path(merged_dir)])
    return merge_args


def display_command(runtime: PlatformRuntime, args: list[str]) -> str:
    return runtime.format_command(args)


def _render_progress_html(
    runtime: PlatformRuntime,
    workers: list[WorkerPlan],
    progress_html_path: Path,
) -> None:
    args = [
        runtime.python_executable,
        runtime.path("scripts/render_full_api_progress_html.py"),
        "--run-dirs",
    ]
    args.extend(runtime.path(worker.run_dir) for worker in workers)
    args.extend(["--output", runtime.path(progress_html_path)])
    subprocess.run(args, check=False, text=True, capture_output=True)


def _write_terminal_summary(run_root: Path, status: str, return_code: int) -> int:
    update_manifest(run_root, status=status)
    write_summary(run_root)
    return return_code


def _run_seed(worker: WorkerPlan, run_root: Path) -> str:
    if worker.seed_args is None:
        return "0"
    result = subprocess.run(worker.seed_args, check=False, text=True, capture_output=True)
    if result.returncode == 0:
        append_event(
            run_root,
            stage="scenario_generation",
            status="completed",
            message=f"Seeded queries for {worker.model}.",
            model=worker.model,
            details={"safe_name": worker.safe_name, "seeded_query_count": worker.seeded_query_count},
        )
        return "0"

    message = f"Seed query command failed for {worker.model} with exit code {result.returncode}."
    print(message, file=sys.stderr)
    if getattr(result, "stderr", ""):
        print(result.stderr, file=sys.stderr)
    worker.run_dir.mkdir(parents=True, exist_ok=True)
    (worker.run_dir / "worker_exit_code.txt").write_text(str(result.returncode), encoding="utf-8")
    append_event(
        run_root,
        stage="scenario_generation",
        status="failed",
        message=message,
        model=worker.model,
        details={"safe_name": worker.safe_name, "stdout": result.stdout, "stderr": result.stderr},
    )
    write_event(
        run_root,
        level="error",
        event_type="stage_failed",
        stage="scenario_generation",
        model=worker.model,
        message=message,
        details={"safe_name": worker.safe_name, "returncode": result.returncode},
        source=OPS_SOURCE,
    )
    return str(result.returncode)


def _run_seed_phase(run_root: Path, workers: list[WorkerPlan]) -> dict[str, str]:
    exit_codes: dict[str, str] = {}
    for worker in workers:
        seed_exit_code = _run_seed(worker, run_root)
        if seed_exit_code != "0":
            exit_codes[worker.safe_name] = seed_exit_code
            return exit_codes
    return exit_codes


def _wait_for_workers(
    *,
    runtime: PlatformRuntime,
    run_root: Path,
    workers: list[WorkerPlan],
    progress_html_path: Path,
    monitor_interval_seconds: int,
) -> dict[str, str]:
    seed_exit_codes = _run_seed_phase(run_root, workers)
    if seed_exit_codes:
        return seed_exit_codes

    pending = []
    exit_codes: dict[str, str] = {}
    for worker in workers:
        worker.run_dir.mkdir(parents=True, exist_ok=True)
        worker.cache_path.parent.mkdir(parents=True, exist_ok=True)
        append_event(
            run_root,
            stage="answer",
            status="running",
            message=f"Worker running for {worker.model}.",
            model=worker.model,
            details={"safe_name": worker.safe_name},
        )
        handle = runtime.launch_worker(worker.python_args, cwd=Path.cwd(), log_path=worker.run_dir / "worker.log")
        pending.append((worker, handle))

    while pending:
        remaining = []
        for worker, handle in pending:
            process = getattr(handle, "process", None)
            poll = getattr(process, "poll", None)
            exit_code = 0 if process is None or not callable(poll) else poll()
            if exit_code is None:
                remaining.append((worker, handle))
                continue

            exit_text = str(exit_code)
            exit_codes[worker.safe_name] = exit_text
            worker.run_dir.mkdir(parents=True, exist_ok=True)
            (worker.run_dir / "worker_exit_code.txt").write_text(exit_text, encoding="utf-8")
            if exit_text == "0":
                append_event(
                    run_root,
                    stage="answer",
                    status="completed",
                    message=f"Worker completed for {worker.model}.",
                    model=worker.model,
                    details={"safe_name": worker.safe_name, "exit_code": exit_text},
                )
            else:
                append_event(
                    run_root,
                    stage="answer",
                    status="failed",
                    message=f"Worker failed for {worker.model} with exit code {exit_text}.",
                    model=worker.model,
                    details={"safe_name": worker.safe_name, "exit_code": exit_text},
                )
                write_event(
                    run_root,
                    level="error",
                    event_type="worker_failed",
                    stage="answer",
                    model=worker.model,
                    message=f"Worker failed for {worker.model} with exit code {exit_text}.",
                    details={"safe_name": worker.safe_name, "exit_code": exit_text},
                    source=OPS_SOURCE,
                )

        pending = remaining
        _render_progress_html(runtime, workers, progress_html_path)
        if pending:
            time.sleep(monitor_interval_seconds)

    return exit_codes


def _classify_runs(
    runtime: PlatformRuntime,
    workers: list[WorkerPlan],
    exit_code_path: Path,
) -> dict:
    args = [runtime.python_executable, runtime.path("scripts/full_api_run_status.py")]
    for worker in workers:
        args.extend(["--run-dir", runtime.path(worker.run_dir)])
    args.extend(["--exit-code-file", runtime.path(exit_code_path)])
    result = subprocess.run(args, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"Run status classification failed: {result.stderr}")
    return json.loads(result.stdout)


def print_dry_run(
    options: RunnerOptions,
    runtime: PlatformRuntime,
    run_root: Path,
    progress_html_path: Path,
    workers: list[WorkerPlan],
    merge_args: list[str],
    models: list[str],
) -> None:
    print("DRY RUN: full API parallel run with monitoring")
    print(f"Run root: {runtime.path(run_root)}")
    print(f"Run mode: {options.run_mode}")
    print(f"Queries per model: {options.queries_per_model}")
    print(f"Selected models: {', '.join(models)}")
    print(f"Progress HTML: {runtime.path(progress_html_path)}")
    print(f"Pipeline manifest: {runtime.path(run_root / 'run_manifest.json')}")
    print(f"Pipeline state: {runtime.path(run_root / 'pipeline_state.jsonl')}")
    if options.seed_queries_run_dir:
        print(f"Seed queries run: {runtime.path(options.seed_queries_run_dir)}")
        print("Scenario generation will resume from seeded api_queries.csv")
    print()

    for worker in workers:
        print(f"Model: {worker.model}")
        print(f"Run dir: {runtime.path(worker.run_dir)}")
        print(f"Cache: {runtime.path(worker.cache_path)}")
        if options.seed_queries_run_dir:
            print(f"Seeded queries: {worker.seeded_query_count}")
            if worker.seed_args is not None:
                print(f"Seed command: {display_command(runtime, worker.seed_args)}")
        print(display_command(runtime, worker.python_args))
        print(f"Watch: {display_command(runtime, worker.watch_args)}")
        print()

    print("Merge:")
    if options.skip_merge:
        print(f"Skip merge set. Merge command: {display_command(runtime, merge_args)}")
    else:
        print(display_command(runtime, merge_args))


def run(options: RunnerOptions, runtime: PlatformRuntime | None = None) -> int:
    runtime = runtime or detect_platform(options.platform)
    models = selected_models(options)
    run_root = build_run_root(options)
    progress_html_path = Path(options.progress_html_path) if options.progress_html_path else run_root / "progress.html"
    workers = build_worker_plans(options, runtime, run_root, models)
    merge_args = build_merge_args(options, runtime, workers, run_root / "merged")

    if options.dry_run:
        print_dry_run(options, runtime, run_root, progress_html_path, workers, merge_args, models)
        return 0

    initialize_manifest(
        run_root=run_root,
        run_type="full_api_parallel",
        stages=PIPELINE_STAGES,
        models=models,
        metadata={"run_mode": options.run_mode, "queries_per_model": options.queries_per_model},
    )
    write_event(
        run_root,
        level="info",
        event_type="run_started",
        message="Full API parallel run started.",
        details={"run_mode": options.run_mode, "queries_per_model": options.queries_per_model, "models": models},
        source=OPS_SOURCE,
    )
    append_event(run_root, stage="answer", status="running", message="Full API workers starting.")
    _render_progress_html(runtime, workers, progress_html_path)

    exit_codes = _wait_for_workers(
        runtime=runtime,
        run_root=run_root,
        workers=workers,
        progress_html_path=progress_html_path,
        monitor_interval_seconds=options.monitor_interval_seconds,
    )
    exit_code_path = run_root / "worker_exit_codes.json"
    exit_code_path.write_text(json.dumps(exit_codes, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    try:
        classification = _classify_runs(runtime, workers, exit_code_path)
    except (RuntimeError, json.JSONDecodeError) as exc:
        append_event(run_root, stage="answer", status="failed", message=str(exc))
        write_event(
            run_root,
            level="error",
            event_type="stage_failed",
            stage="answer",
            message=str(exc),
            source=OPS_SOURCE,
        )
        return _write_terminal_summary(run_root, "failed", 1)

    fatal_count = int(classification.get("fatal_count") or 0)
    warning_count = int(classification.get("warning_count") or 0)
    if fatal_count > 0:
        append_event(
            run_root,
            stage="answer",
            status="failed",
            message=f"Run status classifier found {fatal_count} fatal model issue(s).",
            details=classification,
        )
        write_event(
            run_root,
            level="error",
            event_type="stage_failed",
            stage="answer",
            message=f"Run status classifier found {fatal_count} fatal model issue(s).",
            details=classification,
            source=OPS_SOURCE,
        )
        _render_progress_html(runtime, workers, progress_html_path)
        return _write_terminal_summary(run_root, "failed", 1)

    if warning_count > 0:
        append_event(
            run_root,
            stage="answer",
            status="complete_with_model_warnings",
            message=f"Workers completed with {warning_count} model warning(s).",
            details=classification,
        )
        write_event(
            run_root,
            level="warning",
            event_type="stage_completed",
            stage="answer",
            message=f"Workers completed with {warning_count} model warning(s).",
            details=classification,
            source=OPS_SOURCE,
        )
    else:
        append_event(run_root, stage="answer", status="completed", message="All workers completed.", details=classification)
        write_event(
            run_root,
            level="info",
            event_type="stage_completed",
            stage="answer",
            message="All workers completed.",
            details=classification,
            source=OPS_SOURCE,
        )

    if options.skip_merge:
        append_event(run_root, stage="merge", status="skipped", message="Merge skipped by option.")
        write_event(
            run_root,
            level="info",
            event_type="run_completed",
            message="Full API parallel run completed with merge skipped.",
            source=OPS_SOURCE,
        )
        _render_progress_html(runtime, workers, progress_html_path)
        return _write_terminal_summary(run_root, "completed", 0)

    append_event(run_root, stage="merge", status="running", message="Merging model runs.")
    merge_result = subprocess.run(merge_args, check=False, text=True, capture_output=True)
    if merge_result.returncode != 0:
        message = f"Merge failed with exit code {merge_result.returncode}."
        append_event(
            run_root,
            stage="merge",
            status="failed",
            message=message,
            details={"stdout": merge_result.stdout, "stderr": merge_result.stderr},
        )
        write_event(
            run_root,
            level="error",
            event_type="stage_failed",
            stage="merge",
            message=message,
            details={"stdout": merge_result.stdout, "stderr": merge_result.stderr},
            source=OPS_SOURCE,
        )
        _render_progress_html(runtime, workers, progress_html_path)
        return _write_terminal_summary(run_root, "failed", 1)

    append_event(run_root, stage="merge", status="completed", message="Merged model runs.")
    append_event(run_root, stage="report", status="completed", message="Merged report ready.")
    write_event(
        run_root,
        level="info",
        event_type="run_completed",
        message="Full API parallel run completed.",
        details={"merged_report": str(run_root / "merged" / "competitive_gap_report.md")},
        source=OPS_SOURCE,
    )
    _render_progress_html(runtime, workers, progress_html_path)
    update_manifest(run_root, status="completed")
    write_summary(run_root)
    print(f"Merged report: {runtime.path(run_root / 'merged' / 'competitive_gap_report.md')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
