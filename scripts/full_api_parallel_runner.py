from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
    command: str
    watch_command: str
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
        workers.append(
            WorkerPlan(
                model=model,
                safe_name=model_safe_name,
                run_dir=run_dir,
                cache_path=cache_path,
                command=runtime.format_command(python_args),
                watch_command=runtime.format_command(watch_args),
                seeded_query_count=len(
                    get_seed_queries(options.seed_queries_run_dir, model, options.queries_per_model)
                )
                if options.seed_queries_run_dir
                else 0,
            )
        )

    return workers


def build_merge_command(
    options: RunnerOptions,
    runtime: PlatformRuntime,
    workers: list[WorkerPlan],
    merged_dir: Path,
) -> str:
    merge_args = [
        runtime.python_executable,
        runtime.path("scripts/merge_full_api_runs.py"),
        "--config",
        runtime.path(options.config),
        "--runs",
    ]
    merge_args.extend(runtime.path(worker.run_dir) for worker in workers)
    merge_args.extend(["--output-dir", runtime.path(merged_dir)])
    return runtime.format_command(merge_args)


def print_dry_run(
    options: RunnerOptions,
    runtime: PlatformRuntime,
    run_root: Path,
    progress_html_path: Path,
    workers: list[WorkerPlan],
    merge_command: str,
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
        print(worker.command)
        print(f"Watch: {worker.watch_command}")
        print()

    print("Merge:")
    if options.skip_merge:
        print(f"Skip merge set. Merge command: {merge_command}")
    else:
        print(merge_command)


def run(options: RunnerOptions) -> int:
    runtime = detect_platform(options.platform)
    models = selected_models(options)
    run_root = build_run_root(options)
    progress_html_path = Path(options.progress_html_path) if options.progress_html_path else run_root / "progress.html"
    workers = build_worker_plans(options, runtime, run_root, models)
    merge_command = build_merge_command(options, runtime, workers, run_root / "merged")

    if options.dry_run:
        print_dry_run(options, runtime, run_root, progress_html_path, workers, merge_command, models)
        return 0

    print("Non-dry-run execution is not implemented in Task 2; use --dry-run.", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
