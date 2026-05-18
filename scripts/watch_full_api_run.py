from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TASK_ORDER = ["scenario_generation", "rerank", "answer"]
RUN_PREFIX = "client_acquisition_simulator_full_api_"
DEFAULT_PERSONAS = ["SaaS founder", "SEO agency owner", "local business owner"]
DEFAULT_JOURNEY_STAGES = [
    "problem_aware",
    "solution_aware",
    "vendor_discovery",
    "trust_validation",
    "objection_handling",
]


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_csv_rows(path: Path, warnings: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        warnings.append(f"Missing {path.name}")
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path, warnings: list[str]) -> dict[str, Any]:
    if not path.exists():
        warnings.append(f"Missing {path.name}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        warnings.append(f"Could not parse {path.name}: {exc}")
        return {}


def read_jsonl(path: Path, warnings: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        warnings.append(f"Missing {path.name}")
        return []
    rows: list[dict[str, Any]] = []
    bad_lines = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad_lines += 1
    if bad_lines:
        warnings.append(f"Skipped {bad_lines} malformed rows in {path.name}")
    return rows


def count_rows(path: Path, warnings: list[str]) -> int:
    return len(read_csv_rows(path, warnings))


def blank_counter() -> dict[str, Any]:
    return {
        "attempts": 0,
        "api_calls": 0,
        "cache_hits": 0,
        "failures": 0,
        "terminal_calls": 0,
        "last_activity_at": "",
    }


def increment_counter(counter: dict[str, Any], attempt: dict[str, Any]) -> None:
    status = str(attempt.get("status", "")).lower()
    cache_hit = str(attempt.get("cache_hit", "")).lower() == "true"
    counter["attempts"] += 1
    if status == "api_call":
        counter["api_calls"] += 1
        counter["terminal_calls"] += 1
    elif status == "cache_hit" or cache_hit:
        counter["cache_hits"] += 1
        counter["terminal_calls"] += 1
    elif status == "error":
        counter["failures"] += 1
        counter["terminal_calls"] += 1
    else:
        counter["terminal_calls"] += 1

    created_at = parse_datetime(attempt.get("created_at"))
    current = parse_datetime(counter.get("last_activity_at"))
    if created_at and (current is None or created_at > current):
        counter["last_activity_at"] = created_at.isoformat().replace("+00:00", "Z")


def expected_counts(config: dict[str, Any], actual_queries: int) -> dict[str, int]:
    models = list(config.get("models", []) or [])
    model_count = len(models)
    client_config = config.get("client_acquisition", {}) if isinstance(config.get("client_acquisition"), dict) else {}
    personas = list(client_config.get("personas") or DEFAULT_PERSONAS)
    stages = list(client_config.get("journey_stages") or DEFAULT_JOURNEY_STAGES)
    queries_per_model = int(client_config.get("queries_per_model") or 0)
    queries_per_stage = int(client_config.get("queries_per_stage") or 1)
    expected_queries = model_count * queries_per_model if queries_per_model else model_count * len(personas) * len(stages) * queries_per_stage
    if expected_queries == 0:
        expected_queries = actual_queries
    return {
        "scenario_generation": model_count * len(personas) * len(stages),
        "rerank": expected_queries,
        "answer": expected_queries,
    }


def file_activity_time(run_dir: Path) -> datetime | None:
    latest: datetime | None = None
    for path in run_dir.glob("*"):
        if not path.is_file():
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if latest is None or modified > latest:
            latest = modified
    return latest


def summarize_run(
    run_dir: Path | str,
    now: datetime | None = None,
    stall_after_seconds: int = 900,
) -> dict[str, Any]:
    run_path = Path(run_dir)
    now = now or datetime.now(timezone.utc)
    warnings: list[str] = []

    config = read_json(run_path / "run_config.resolved.json", warnings)
    query_rows = read_csv_rows(run_path / "api_queries.csv", warnings)
    retrieval_rows = read_csv_rows(run_path / "retrieval_by_model.csv", warnings)
    answer_rows = read_csv_rows(run_path / "model_answer_evaluations.csv", warnings)
    api_summary_rows = read_csv_rows(run_path / "api_call_summary.csv", warnings)
    attempts = read_jsonl(run_path / "api_orchestrator_attempts.jsonl", warnings)

    tasks: dict[str, dict[str, Any]] = defaultdict(blank_counter)
    models: dict[str, dict[str, Any]] = defaultdict(blank_counter)
    failures: list[dict[str, str]] = []
    first_activity: datetime | None = None
    last_activity: datetime | None = None

    for attempt in attempts:
        task_type = str(attempt.get("task_type") or "unknown")
        model = str(attempt.get("model") or "unknown")
        increment_counter(tasks[task_type], attempt)
        increment_counter(models[model], attempt)

        created_at = parse_datetime(attempt.get("created_at"))
        if created_at:
            if first_activity is None or created_at < first_activity:
                first_activity = created_at
            if last_activity is None or created_at > last_activity:
                last_activity = created_at

        if str(attempt.get("status", "")).lower() == "error" and len(failures) < 5:
            failures.append(
                {
                    "task_type": task_type,
                    "model": model,
                    "query_id": str(attempt.get("query_id") or ""),
                    "error": str(attempt.get("error") or ""),
                }
            )

    if last_activity is None:
        last_activity = file_activity_time(run_path)
    expected_by_task = expected_counts(config, len(query_rows))
    expected_total = sum(expected_by_task.values())
    expected_queries = max(expected_by_task.get("rerank", 0), expected_by_task.get("answer", 0), len(query_rows))
    terminal_calls = sum(int(row["terminal_calls"]) for row in tasks.values())
    api_calls = sum(int(row["api_calls"]) for row in tasks.values())
    cache_hits = sum(int(row["cache_hits"]) for row in tasks.values())
    failure_count = sum(int(row["failures"]) for row in tasks.values())
    progress = terminal_calls / expected_total if expected_total else 0.0
    idle_seconds = int((now - last_activity).total_seconds()) if last_activity else None

    if not attempts and not query_rows and not retrieval_rows and not answer_rows:
        status = "empty"
    elif expected_total and terminal_calls >= expected_total and failure_count:
        status = "complete_with_failures"
    elif expected_total and terminal_calls >= expected_total:
        status = "complete"
    elif idle_seconds is not None and idle_seconds > stall_after_seconds:
        status = "likely_stalled"
    else:
        status = "active"

    ordered_tasks = {
        key: tasks[key]
        for key in TASK_ORDER + sorted(set(tasks) - set(TASK_ORDER))
        if key in tasks
    }
    return {
        "run_dir": str(run_path),
        "status": status,
        "totals": {
            "queries": len(query_rows),
            "expected_api_calls": expected_total,
            "terminal_calls": terminal_calls,
            "api_calls": api_calls,
            "cache_hits": cache_hits,
            "failures": failure_count,
            "progress": progress,
        },
        "expected_by_task": expected_by_task,
        "outputs": {
            "query_rows": len(query_rows),
            "retrieval_rows": len(retrieval_rows),
            "answer_rows": len(answer_rows),
            "api_summary_rows": len(api_summary_rows),
            "report_exists": (run_path / "competitive_gap_report.md").exists(),
        },
        "missing": {
            "queries": max(expected_queries - len(query_rows), 0),
            "retrieval_rows": max(expected_queries - len(retrieval_rows), 0),
            "answer_rows": max(expected_queries - len(answer_rows), 0),
            "terminal_calls": max(expected_total - terminal_calls, 0),
        },
        "tasks": ordered_tasks,
        "models": dict(sorted(models.items())),
        "failures": failures,
        "timing": {
            "first_activity_at": first_activity.isoformat().replace("+00:00", "Z") if first_activity else "",
            "last_activity_at": last_activity.isoformat().replace("+00:00", "Z") if last_activity else "",
            "idle_seconds": idle_seconds,
            "elapsed_seconds": int((last_activity - first_activity).total_seconds()) if first_activity and last_activity else None,
        },
        "warnings": warnings,
    }


def pct(value: float) -> str:
    return f"{value:.1%}"


def format_text_report(summary: dict[str, Any]) -> str:
    totals = summary["totals"]
    lines = [
        f"Run: {summary['run_dir']}",
        f"Status: {summary['status']}",
        f"Progress: {totals['terminal_calls']}/{totals['expected_api_calls']} terminal calls ({pct(totals['progress'])})",
        f"API calls: {totals['api_calls']} | Cache hits: {totals['cache_hits']} | Failures: {totals['failures']}",
        f"Queries: {totals['queries']} | Retrieval rows: {summary['outputs']['retrieval_rows']} | Answer rows: {summary['outputs']['answer_rows']}",
        f"Missing: retrieval {summary['missing']['retrieval_rows']}, answers {summary['missing']['answer_rows']}, terminal calls {summary['missing']['terminal_calls']}",
        f"Last activity: {summary['timing']['last_activity_at'] or 'unknown'} | Idle seconds: {summary['timing']['idle_seconds']}",
        "",
        "Tasks:",
    ]
    if summary["tasks"]:
        for task_type, row in summary["tasks"].items():
            expected = summary["expected_by_task"].get(task_type, 0)
            lines.append(
                f"- {task_type}: {row['terminal_calls']}/{expected} terminal, "
                f"api {row['api_calls']}, cache {row['cache_hits']}, failures {row['failures']}"
            )
    else:
        lines.append("- No task attempts found.")

    lines.extend(["", "Models:"])
    if summary["models"]:
        for model, row in summary["models"].items():
            lines.append(
                f"- {model}: {row['terminal_calls']} terminal, api {row['api_calls']}, "
                f"cache {row['cache_hits']}, failures {row['failures']}"
            )
    else:
        lines.append("- No model attempts found.")

    lines.extend(["", "Failures:"])
    if summary["failures"]:
        for failure in summary["failures"]:
            lines.append(
                f"- {failure['task_type']} | {failure['model']} | {failure['query_id']}: {failure['error']}"
            )
    else:
        lines.append("- None in observed orchestrator attempts.")

    if summary["warnings"]:
        lines.extend(["", "Warnings:"])
        for warning in summary["warnings"]:
            lines.append(f"- {warning}")
    return "\n".join(lines) + "\n"


def find_latest_run(runs_root: Path | str = Path("runs")) -> Path:
    root = Path(runs_root)
    matches = sorted(path for path in root.iterdir() if path.is_dir() and path.name.startswith(RUN_PREFIX))
    if not matches:
        raise FileNotFoundError(f"No {RUN_PREFIX}* directories found under {root}")
    return matches[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch a full API client acquisition simulator run without modifying it.")
    parser.add_argument("--run-dir", default=None, help="Run directory to inspect.")
    parser.add_argument("--latest", action="store_true", help="Inspect the latest full API run under --runs-root.")
    parser.add_argument("--runs-root", default="runs", help="Root directory used by --latest.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--stall-after-seconds", type=int, default=900)
    args = parser.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else find_latest_run(Path(args.runs_root))
    summary = summarize_run(run_dir, stall_after_seconds=args.stall_after_seconds)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_text_report(summary), end="")


if __name__ == "__main__":
    main()
