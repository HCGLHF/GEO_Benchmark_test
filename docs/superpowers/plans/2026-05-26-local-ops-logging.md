# Local Ops Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local, run-directory-based operations logging layer with structured events, health summaries, CLI inspection, and Run Monitor integration.

**Architecture:** Keep existing run facts authoritative and add an additive operations layer under each run root. `scripts/ops_logging.py` owns event and summary contracts, `scripts/ops_logs.py` exposes CLI inspection, and existing runners write operations events at critical lifecycle points without changing benchmark metrics.

**Tech Stack:** Python standard library, pytest, PowerShell launcher scripts, existing JSONL/CSV run artifacts, local UI Monitor.

---

## File Structure

- Create `scripts/ops_logging.py`: structured operations event writer, event reader/filter, and summary generator.
- Create `scripts/ops_logs.py`: CLI for `record`, `summary`, `events`, and `doctor`.
- Create `tests/test_ops_logging.py`: unit tests for event writing/filtering and summary generation.
- Create `tests/test_ops_logs_cli.py`: subprocess tests for CLI commands.
- Modify `scripts/run_pipeline_step.py`: write operations events for stage lifecycle.
- Modify `tests/test_run_pipeline_step.py`: assert operations events exist for success and failure.
- Modify `scripts/geo_eval/orchestrator.py`: write operations events for API failures.
- Modify `tests/test_orchestrator.py`: assert failed model calls append `api_failure`.
- Modify `scripts/run_full_api_parallel_with_watch.ps1`: call the Python CLI for top-level run/worker/merge/report operations events and summary refresh.
- Modify `tests/test_full_api_parallel_with_watch.py`: assert the PowerShell runner contains operations logging hooks.
- Modify `scripts/ui_app/run_monitor.py`: prefer `ops_summary.json` when present while preserving fallback health inference.
- Modify `scripts/ui_app/server.py`: render recommended actions when present in monitor health.
- Modify `tests/test_ui_run_monitor.py`: assert summary preference and fallback behavior.
- Modify `docs/ui-console.md`: document local operations log files and CLI commands.
- Modify `docs/architecture.md`: record the operations logging boundary.
- Modify `docs/risks.md`: record local log retention and self-contained run-root risks.
- Modify `docs/next.md`: record completed work, learned details, residual risks, and next steps.

---

### Task 1: Structured Operations Event Core

**Files:**
- Create: `scripts/ops_logging.py`
- Create: `tests/test_ops_logging.py`

- [ ] **Step 1: Write failing tests for event writing and filtering**

Add `tests/test_ops_logging.py`:

```python
import json
from pathlib import Path

from scripts.ops_logging import filter_events, read_events, write_event


def test_write_event_appends_stable_jsonl_record(tmp_path: Path) -> None:
    run_root = tmp_path / "run"

    event = write_event(
        run_root,
        level="warning",
        event_type="api_failure",
        stage="answer",
        model="openai/gpt-4.1-mini",
        message="Provider returned 429.",
        details={"query_id": "q001", "error": "429 Too Many Requests"},
        source="tests",
    )

    rows = (run_root / "ops_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    parsed = json.loads(rows[0])
    assert parsed["created_at"].endswith("Z")
    assert parsed["level"] == "warning"
    assert parsed["event_type"] == "api_failure"
    assert parsed["run_root"] == str(run_root)
    assert parsed["stage"] == "answer"
    assert parsed["model"] == "openai/gpt-4.1-mini"
    assert parsed["message"] == "Provider returned 429."
    assert parsed["details"] == {"query_id": "q001", "error": "429 Too Many Requests"}
    assert parsed["source"] == "tests"
    assert event == parsed


def test_filter_events_by_level_event_type_and_model(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    write_event(run_root, level="info", event_type="stage_started", model="", message="Started")
    write_event(run_root, level="error", event_type="worker_failed", model="model-a", message="Worker failed")
    write_event(run_root, level="error", event_type="api_failure", model="model-b", message="API failed")

    assert [event["event_type"] for event in filter_events(run_root, level="error")] == [
        "worker_failed",
        "api_failure",
    ]
    assert [event["model"] for event in filter_events(run_root, event_type="api_failure")] == ["model-b"]
    assert [event["event_type"] for event in filter_events(run_root, model="model-a")] == ["worker_failed"]


def test_read_events_skips_malformed_rows(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "ops_events.jsonl").write_text(
        '{"level":"info","event_type":"run_started"}\nnot-json\n{"level":"error","event_type":"worker_failed"}\n',
        encoding="utf-8",
    )

    assert [event["event_type"] for event in read_events(run_root)] == ["run_started", "worker_failed"]
```

- [ ] **Step 2: Run the focused failing tests**

Run:

```powershell
pytest tests\test_ops_logging.py -q
```

Expected: FAIL because `scripts.ops_logging` does not exist.

- [ ] **Step 3: Implement event writing, reading, and filtering**

Create `scripts/ops_logging.py` with:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVENTS_NAME = "ops_events.jsonl"
SUMMARY_NAME = "ops_summary.json"
LEVELS = {"debug", "info", "warning", "error"}
EVENT_TYPES = {
    "run_started",
    "run_completed",
    "stage_started",
    "stage_completed",
    "stage_failed",
    "api_failure",
    "worker_failed",
    "output_missing",
    "resume_started",
    "summary_generated",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_level(level: str) -> str:
    value = str(level or "info").strip().lower()
    return value if value in LEVELS else "info"


def _clean_event_type(event_type: str) -> str:
    value = str(event_type or "").strip().lower()
    if value not in EVENT_TYPES:
        raise ValueError(f"Unsupported ops event type: {event_type}")
    return value


def write_event(
    run_root: Path | str,
    *,
    level: str = "info",
    event_type: str,
    stage: str = "",
    model: str = "",
    message: str = "",
    details: dict[str, Any] | None = None,
    source: str = "",
) -> dict[str, Any]:
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    event = {
        "created_at": utc_now(),
        "level": _clean_level(level),
        "event_type": _clean_event_type(event_type),
        "run_root": str(run_root),
        "stage": str(stage or ""),
        "model": str(model or ""),
        "message": str(message or ""),
        "details": details or {},
        "source": str(source or ""),
    }
    with (root / EVENTS_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def safe_write_event(run_root: Path | str, **kwargs: Any) -> dict[str, Any] | None:
    try:
        return write_event(run_root, **kwargs)
    except Exception:
        return None


def read_events(run_root: Path | str) -> list[dict[str, Any]]:
    path = Path(run_root) / EVENTS_NAME
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def filter_events(
    run_root: Path | str,
    *,
    level: str = "",
    event_type: str = "",
    model: str = "",
) -> list[dict[str, Any]]:
    rows = read_events(run_root)
    if level:
        rows = [row for row in rows if str(row.get("level") or "") == level]
    if event_type:
        rows = [row for row in rows if str(row.get("event_type") or "") == event_type]
    if model:
        rows = [row for row in rows if str(row.get("model") or "") == model]
    return rows
```

- [ ] **Step 4: Run the focused tests**

Run:

```powershell
pytest tests\test_ops_logging.py -q
```

Expected: PASS for the event tests.

- [ ] **Step 5: Commit**

```powershell
git add scripts/ops_logging.py tests/test_ops_logging.py
git commit -m "feat: add local ops event logging"
```

---

### Task 2: Operations Summary Generation

**Files:**
- Modify: `scripts/ops_logging.py`
- Modify: `tests/test_ops_logging.py`

- [ ] **Step 1: Add failing summary tests**

Append to `tests/test_ops_logging.py`:

```python
from scripts.pipeline_state import append_event, initialize_manifest
from scripts.ops_logging import generate_summary, write_summary


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_generate_summary_reports_ok_for_completed_pipeline_run(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    initialize_manifest(run_root=run_root, run_type="ui_pipeline", stages=["clean", "report"])
    append_event(run_root, stage="clean", status="completed", message="Cleaned")
    append_event(run_root, stage="report", status="completed", message="Report ready")

    summary = generate_summary(run_root)

    assert summary["status"] == "ok"
    assert summary["current_stage"] == ""
    assert summary["issues"] == []
    assert summary["recommended_actions"] == []
    assert summary["key_files"]["pipeline_state"] == "pipeline_state.jsonl"
    assert summary["key_files"]["ops_events"] == "ops_events.jsonl"


def test_generate_summary_reports_error_for_failed_worker_with_incomplete_outputs(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    model_dir = run_root / "openai_gpt-4.1-mini"
    model_dir.mkdir(parents=True)
    (model_dir / "run_config.resolved.json").write_text(
        json.dumps(
            {
                "models": [{"provider": "openrouter", "model": "openai/gpt-4.1-mini"}],
                "client_acquisition": {"queries_per_model": 1},
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "api_queries.csv").write_text("query_id,query\nq001,Need GEO\n", encoding="utf-8")
    (model_dir / "worker_exit_code.txt").write_text("1", encoding="utf-8")
    write_jsonl(
        model_dir / "api_orchestrator_attempts.jsonl",
        [
            {
                "task_type": "answer",
                "model": "openai/gpt-4.1-mini",
                "status": "error",
                "query_id": "q001",
                "error": "402 Payment Required",
            }
        ],
    )

    summary = generate_summary(run_root)

    assert summary["status"] == "error"
    assert any("openai_gpt-4.1-mini exited with code 1" in issue for issue in summary["issues"])
    assert any("Payment required" in action for action in summary["recommended_actions"])
    assert "openai_gpt-4.1-mini/worker.log" in summary["key_files"]["worker_logs"]


def test_generate_summary_reports_warning_for_rate_limit_with_complete_outputs(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    model_dir = run_root / "qwen_qwen3.7-max"
    model_dir.mkdir(parents=True)
    (model_dir / "run_config.resolved.json").write_text(
        json.dumps(
            {
                "models": [{"provider": "openrouter", "model": "qwen/qwen3.7-max"}],
                "client_acquisition": {"queries_per_model": 1},
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "api_queries.csv").write_text("query_id,query\nq001,Need GEO\n", encoding="utf-8")
    (model_dir / "retrieval_by_model.csv").write_text("query_id,model\nq001,qwen/qwen3.7-max\n", encoding="utf-8")
    (model_dir / "model_answer_evaluations.csv").write_text(
        "query_id,model,error\nq001,qwen/qwen3.7-max,\n",
        encoding="utf-8",
    )
    (model_dir / "worker_exit_code.txt").write_text("0", encoding="utf-8")
    write_jsonl(
        model_dir / "api_orchestrator_attempts.jsonl",
        [
            {"task_type": "rerank", "model": "qwen/qwen3.7-max", "status": "api_call"},
            {"task_type": "answer", "model": "qwen/qwen3.7-max", "status": "api_call"},
            {
                "task_type": "answer",
                "model": "qwen/qwen3.7-max",
                "status": "error",
                "query_id": "q001",
                "error": "429 Too Many Requests",
            },
        ],
    )

    summary = generate_summary(run_root)

    assert summary["status"] == "warning"
    assert any("rate-limit" in issue for issue in summary["issues"])
    assert any("backoff" in action.lower() for action in summary["recommended_actions"])


def test_write_summary_persists_summary_and_records_summary_event(tmp_path: Path) -> None:
    run_root = tmp_path / "run"

    summary = write_summary(run_root)

    assert (run_root / "ops_summary.json").exists()
    assert json.loads((run_root / "ops_summary.json").read_text(encoding="utf-8")) == summary
    assert any(event["event_type"] == "summary_generated" for event in read_events(run_root))
```

- [ ] **Step 2: Run the focused failing summary tests**

Run:

```powershell
pytest tests\test_ops_logging.py -q
```

Expected: FAIL because summary functions are not implemented.

- [ ] **Step 3: Implement summary helpers**

Append these functions and imports to `scripts/ops_logging.py`:

```python
from scripts.full_api_run_status import summarize_run_dir
from scripts.pipeline_state import read_pipeline_status


def _relative_to_run(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _model_dirs(root: Path) -> list[Path]:
    ignored = {"cache", "merged", "logs"}
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir() and path.name not in ignored)


def _read_exit_code(model_dir: Path) -> str:
    path = model_dir / "worker_exit_code.txt"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig").strip()


def _append_once(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _actions_for_text(text: str) -> list[str]:
    lower = text.lower()
    actions: list[str] = []
    if "402" in text or "payment required" in lower:
        actions.append("Payment required detected: stop the run, add API credit, then resume from the known UI launch when applicable.")
    if "429" in text or "too many requests" in lower or "rate limit" in lower or "rate-limit" in lower:
        actions.append("Rate limit detected: wait for provider backoff, then resume from existing outputs if the run was UI-launched.")
    return actions


def _severity_rank(status: str) -> int:
    return {"unknown": 0, "ok": 1, "warning": 2, "stalled": 3, "error": 4}.get(status, 0)


def _max_status(current: str, candidate: str) -> str:
    return candidate if _severity_rank(candidate) > _severity_rank(current) else current


def generate_summary(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    pipeline = read_pipeline_status(root)
    status = "unknown"
    issues: list[str] = []
    actions: list[str] = []
    worker_logs: list[str] = []
    api_summary = ""

    if pipeline.get("manifest") or pipeline.get("events"):
        status = "ok"
    for stage, item in (pipeline.get("stages") or {}).items():
        stage_status = str(item.get("status") or "").lower()
        if stage_status in {"failed", "error"}:
            status = "error"
            issues.append(f"Pipeline stage {stage} failed: {item.get('message') or 'no message'}")
        elif stage_status in {"complete_with_model_warnings", "interrupted"}:
            status = _max_status(status, "warning")
            issues.append(f"Pipeline stage {stage} is {stage_status}: {item.get('message') or 'no message'}")

    for model_dir in _model_dirs(root):
        worker_log = model_dir / "worker.log"
        _append_once(worker_logs, _relative_to_run(root, worker_log))
        if (model_dir / "api_call_summary.csv").exists() and not api_summary:
            api_summary = _relative_to_run(root, model_dir / "api_call_summary.csv")
        exit_code = _read_exit_code(model_dir)
        run_status = summarize_run_dir(model_dir, exit_code=exit_code)
        for message in run_status.get("messages") or []:
            _append_once(issues, str(message))
            for action in _actions_for_text(str(message)):
                _append_once(actions, action)
        summary = run_status.get("summary") or {}
        for failure in summary.get("failures") or []:
            text = str(failure.get("error") or "")
            for action in _actions_for_text(text):
                _append_once(actions, action)
        if run_status.get("fatal"):
            status = "error"
            if exit_code and exit_code != "0":
                _append_once(issues, f"{model_dir.name} exited with code {exit_code}.")
        elif run_status.get("warning"):
            status = _max_status(status, "warning")
        if summary.get("status") == "likely_stalled":
            status = _max_status(status, "stalled")
            _append_once(issues, f"{model_dir.name} is likely stalled.")

    for event in read_events(root):
        if str(event.get("level") or "") == "error":
            status = "error"
            _append_once(issues, str(event.get("message") or "Error event recorded."))
        elif str(event.get("level") or "") == "warning":
            status = _max_status(status, "warning")
            _append_once(issues, str(event.get("message") or "Warning event recorded."))
        for action in _actions_for_text(str(event.get("message") or "") + " " + json.dumps(event.get("details") or {})):
            _append_once(actions, action)

    if (root / "merged" / "api_call_summary.csv").exists():
        api_summary = "merged/api_call_summary.csv"
    if status == "unknown" and root.exists():
        status = "ok" if not issues else "warning"

    summary = {
        "status": status,
        "run_root": str(run_root),
        "current_stage": str(pipeline.get("current_stage") or ""),
        "updated_at": utc_now(),
        "issues": issues,
        "recommended_actions": actions,
        "key_files": {
            "pipeline_state": "pipeline_state.jsonl",
            "ops_events": EVENTS_NAME,
            "worker_logs": worker_logs,
            "api_summary": api_summary,
        },
    }
    return summary


def write_summary(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    summary = generate_summary(root)
    (root / SUMMARY_NAME).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_event(
        root,
        level="info",
        event_type="summary_generated",
        message=f"Operations summary generated with status {summary['status']}.",
        details={"status": summary["status"]},
        source="scripts/ops_logging.py",
    )
    return summary


def read_summary(run_root: Path | str) -> dict[str, Any]:
    path = Path(run_root) / SUMMARY_NAME
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
```

- [ ] **Step 4: Run the summary tests**

Run:

```powershell
pytest tests\test_ops_logging.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/ops_logging.py tests/test_ops_logging.py
git commit -m "feat: generate local ops summaries"
```

---

### Task 3: Operations Logs CLI

**Files:**
- Create: `scripts/ops_logs.py`
- Create: `tests/test_ops_logs_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add `tests/test_ops_logs_cli.py`:

```python
import json
import subprocess
from pathlib import Path

from scripts.ops_logging import write_event


def test_ops_logs_summary_generates_missing_summary(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    result = subprocess.run(
        ["python", "scripts/ops_logs.py", "summary", "--run-root", str(run_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert (run_root / "ops_summary.json").exists()


def test_ops_logs_events_filters_errors(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    write_event(run_root, level="info", event_type="run_started", message="Started")
    write_event(run_root, level="error", event_type="worker_failed", model="model-a", message="Failed")

    result = subprocess.run(
        ["python", "scripts/ops_logs.py", "events", "--run-root", str(run_root), "--level", "error"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert [row["event_type"] for row in rows] == ["worker_failed"]


def test_ops_logs_record_writes_event_for_powershell_runner(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    result = subprocess.run(
        [
            "python",
            "scripts/ops_logs.py",
            "record",
            "--run-root",
            str(run_root),
            "--level",
            "warning",
            "--event-type",
            "worker_failed",
            "--stage",
            "answer",
            "--model",
            "model-a",
            "--message",
            "Worker failed.",
            "--details-json",
            '{"exit_code":1}',
            "--source",
            "test",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    event = json.loads(result.stdout)
    assert event["event_type"] == "worker_failed"
    assert event["details"] == {"exit_code": 1}


def test_ops_logs_doctor_prints_human_summary(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    write_event(run_root, level="warning", event_type="api_failure", message="429 Too Many Requests")

    result = subprocess.run(
        ["python", "scripts/ops_logs.py", "doctor", "--run-root", str(run_root)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "status: warning" in result.stdout
    assert "429 Too Many Requests" in result.stdout
    assert "Rate limit detected" in result.stdout
```

- [ ] **Step 2: Run the focused failing CLI tests**

Run:

```powershell
pytest tests\test_ops_logs_cli.py -q
```

Expected: FAIL because `scripts/ops_logs.py` does not exist.

- [ ] **Step 3: Implement the CLI**

Create `scripts/ops_logs.py`:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ops_logging import filter_events, read_summary, write_event, write_summary


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def command_record(args: argparse.Namespace) -> int:
    details = json.loads(args.details_json)
    event = write_event(
        args.run_root,
        level=args.level,
        event_type=args.event_type,
        stage=args.stage,
        model=args.model,
        message=args.message,
        details=details,
        source=args.source,
    )
    print_json(event)
    return 0


def command_summary(args: argparse.Namespace) -> int:
    summary = read_summary(args.run_root) or write_summary(args.run_root)
    print_json(summary)
    return 0


def command_events(args: argparse.Namespace) -> int:
    rows = filter_events(args.run_root, level=args.level, event_type=args.event_type, model=args.model)
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    summary = write_summary(args.run_root)
    print(f"status: {summary['status']}")
    print(f"current_stage: {summary['current_stage'] or '-'}")
    print("")
    print("issues:")
    if summary["issues"]:
        for issue in summary["issues"]:
            print(f"- {issue}")
    else:
        print("- none")
    print("")
    print("recommended_actions:")
    if summary["recommended_actions"]:
        for action in summary["recommended_actions"]:
            print(f"- {action}")
    else:
        print("- none")
    print("")
    print("key_files:")
    for key, value in summary["key_files"].items():
        print(f"- {key}: {value}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect local operations logs for a GEO run root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record")
    record.add_argument("--run-root", required=True)
    record.add_argument("--level", default="info")
    record.add_argument("--event-type", required=True)
    record.add_argument("--stage", default="")
    record.add_argument("--model", default="")
    record.add_argument("--message", default="")
    record.add_argument("--details-json", default="{}")
    record.add_argument("--source", default="scripts/ops_logs.py")
    record.set_defaults(func=command_record)

    summary = subparsers.add_parser("summary")
    summary.add_argument("--run-root", required=True)
    summary.set_defaults(func=command_summary)

    events = subparsers.add_parser("events")
    events.add_argument("--run-root", required=True)
    events.add_argument("--level", default="")
    events.add_argument("--event-type", default="")
    events.add_argument("--model", default="")
    events.set_defaults(func=command_events)

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--run-root", required=True)
    doctor.set_defaults(func=command_doctor)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run CLI tests**

Run:

```powershell
pytest tests\test_ops_logs_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/ops_logs.py tests/test_ops_logs_cli.py
git commit -m "feat: add local ops log CLI"
```

---

### Task 4: Pipeline Step Integration

**Files:**
- Modify: `scripts/run_pipeline_step.py`
- Modify: `tests/test_run_pipeline_step.py`

- [ ] **Step 1: Write failing tests for operations events**

Append to `tests/test_run_pipeline_step.py`:

```python
from scripts.ops_logging import read_events


def test_run_pipeline_step_writes_ops_events_for_success(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    result = subprocess.run(
        [
            "python",
            "scripts/run_pipeline_step.py",
            "--run-root",
            str(run_root),
            "--stage",
            "clean",
            "--",
            "python",
            "-c",
            "print('clean ok')",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    events = read_events(run_root)
    assert [event["event_type"] for event in events] == ["stage_started", "stage_completed"]
    assert events[0]["level"] == "info"
    assert events[1]["details"]["exit_code"] == 0


def test_run_pipeline_step_writes_ops_event_for_failure(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    result = subprocess.run(
        [
            "python",
            "scripts/run_pipeline_step.py",
            "--run-root",
            str(run_root),
            "--stage",
            "index",
            "--",
            "python",
            "-c",
            "raise SystemExit(7)",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 7
    events = read_events(run_root)
    assert [event["event_type"] for event in events] == ["stage_started", "stage_failed"]
    assert events[1]["level"] == "error"
    assert events[1]["details"]["exit_code"] == 7
```

- [ ] **Step 2: Run the focused failing tests**

Run:

```powershell
pytest tests\test_run_pipeline_step.py -q
```

Expected: FAIL because `run_pipeline_step.py` does not write operations events.

- [ ] **Step 3: Integrate operations event writing**

Modify `scripts/run_pipeline_step.py` imports:

```python
from scripts.ops_logging import safe_write_event
from scripts.pipeline_state import append_event
```

Inside `run_step`, immediately after the first `append_event(...)`, add:

```python
    safe_write_event(
        run_root,
        level="info",
        event_type="stage_started",
        stage=stage,
        model=model,
        message=f"Started: {' '.join(command)}",
        details={"log_path": str(log_path), "command": command},
        source="scripts/run_pipeline_step.py",
    )
```

After the second `append_event(...)`, add:

```python
    safe_write_event(
        run_root,
        level="info" if process.returncode == 0 else "error",
        event_type="stage_completed" if process.returncode == 0 else "stage_failed",
        stage=stage,
        model=model,
        message=f"Finished with exit code {process.returncode}",
        details={"exit_code": process.returncode, "log_path": str(log_path)},
        source="scripts/run_pipeline_step.py",
    )
```

- [ ] **Step 4: Run pipeline step tests**

Run:

```powershell
pytest tests\test_run_pipeline_step.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/run_pipeline_step.py tests/test_run_pipeline_step.py
git commit -m "feat: log pipeline operations events"
```

---

### Task 5: API Failure Operations Events

**Files:**
- Modify: `scripts/geo_eval/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing test for API failure ops event**

Append to `tests/test_orchestrator.py`:

```python
import json


def test_orchestrated_model_call_logs_ops_event_on_api_failure(tmp_path: Path):
    def failing_call(model_config, prompt, temperature):
        raise RuntimeError("OpenRouter 429 Too Many Requests")

    orchestrator = ModelCallOrchestrator(
        cache_path=tmp_path / "cache.sqlite",
        run_state_path=tmp_path / "state.sqlite",
        attempts_path=tmp_path / "attempts.jsonl",
        config_hash="config-a",
        matrix_hash="matrix-a",
        corpus_hash="corpus-a",
        uncached_call=failing_call,
    )

    with pytest.raises(RuntimeError):
        orchestrator.call(
            model_config={"provider": "openrouter", "model": "model-a"},
            prompt="prompt",
            temperature=0.2,
            task_type="answer",
            query_id="q001",
            input_hash="input-a",
            prompt_version="answer-v1",
        )

    events = [
        json.loads(line)
        for line in (tmp_path / "ops_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["level"] == "warning"
    assert events[0]["event_type"] == "api_failure"
    assert events[0]["stage"] == "answer"
    assert events[0]["model"] == "model-a"
    assert events[0]["details"]["query_id"] == "q001"
    assert "429" in events[0]["details"]["error"]
```

- [ ] **Step 2: Run focused failing orchestrator tests**

Run:

```powershell
pytest tests\test_orchestrator.py -q
```

Expected: FAIL because API failures do not write operations events.

- [ ] **Step 3: Integrate safe operations event writing**

Modify `scripts/geo_eval/orchestrator.py` imports:

```python
from scripts.ops_logging import safe_write_event
```

Inside the `except Exception as exc:` block in `ModelCallOrchestrator.call`, after `_log_attempt(...)`, add:

```python
            safe_write_event(
                self.attempts_path.parent,
                level="warning",
                event_type="api_failure",
                stage=task_type,
                model=model,
                message=str(exc),
                details={
                    "provider": provider,
                    "model": model,
                    "query_id": query_id,
                    "task_fingerprint": task_fingerprint,
                    "error": str(exc),
                },
                source="scripts/geo_eval/orchestrator.py",
            )
```

- [ ] **Step 4: Run orchestrator tests**

Run:

```powershell
pytest tests\test_orchestrator.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/geo_eval/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: log API failure operations events"
```

---

### Task 6: Parallel Runner Lifecycle Hooks

**Files:**
- Modify: `scripts/run_full_api_parallel_with_watch.ps1`
- Modify: `tests/test_full_api_parallel_with_watch.py`

- [ ] **Step 1: Write failing test for PowerShell hooks**

Append to `tests/test_full_api_parallel_with_watch.py`:

```python
def test_parallel_with_watch_writes_ops_events_and_summary() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert "function Write-OpsEvent" in script_text
    assert "scripts\\ops_logs.py" in script_text
    assert '"record"' in script_text
    assert '"run_started"' in script_text
    assert '"worker_failed"' in script_text
    assert '"run_completed"' in script_text
    assert '"doctor"' in script_text
```

- [ ] **Step 2: Run the focused failing test**

Run:

```powershell
pytest tests\test_full_api_parallel_with_watch.py::test_parallel_with_watch_writes_ops_events_and_summary -q
```

Expected: FAIL because the PowerShell runner has no operations hooks.

- [ ] **Step 3: Add PowerShell helper functions**

In `scripts/run_full_api_parallel_with_watch.ps1`, after `Write-PipelineEvent`, add:

```powershell
function Write-OpsEvent {
  param(
    [string]$RunRootPath,
    [string]$Level,
    [string]$EventType,
    [string]$Stage = "",
    [string]$Model = "",
    [string]$Message = "",
    [string]$DetailsJson = "{}"
  )
  $opsArgs = @(
    "scripts\ops_logs.py",
    "record",
    "--run-root", $RunRootPath,
    "--level", $Level,
    "--event-type", $EventType,
    "--message", $Message,
    "--details-json", $DetailsJson,
    "--source", "scripts/run_full_api_parallel_with_watch.ps1"
  )
  if ($Stage) {
    $opsArgs += @("--stage", $Stage)
  }
  if ($Model) {
    $opsArgs += @("--model", $Model)
  }
  & python @opsArgs | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "Could not write ops event $EventType for $RunRootPath"
  }
}

function Write-OpsSummary {
  param([string]$RunRootPath)
  & python "scripts\ops_logs.py" "doctor" "--run-root" $RunRootPath | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "Could not write ops summary for $RunRootPath"
  }
}
```

- [ ] **Step 4: Add lifecycle event calls**

After `Write-PipelineInit ...`, add:

```powershell
Write-OpsEvent -RunRootPath $root -Level "info" -EventType "run_started" -Message "Full API parallel run started." -DetailsJson "{`"run_mode`":`"$RunMode`",`"queries_per_model`":$QueriesPerModel}"
```

Inside the worker command's failure branch, after the failed pipeline append, add:

```powershell
  python "scripts\ops_logs.py" "record" "--run-root" "$root" "--level" "error" "--event-type" "worker_failed" "--stage" "answer" "--model" "$($worker.Model)" "--message" "Worker failed." "--details-json" "{`"exit_code`":`$exitCode}" "--source" "scripts/run_full_api_parallel_with_watch.ps1" | Out-Null
```

After fatal classification writes the failed pipeline event, add:

```powershell
  Write-OpsEvent -RunRootPath $root -Level "error" -EventType "stage_failed" -Stage "answer" -Message "One or more model workers produced incomplete outputs."
  Write-OpsSummary -RunRootPath $root
```

After warning classification writes `complete_with_model_warnings`, add:

```powershell
  Write-OpsEvent -RunRootPath $root -Level "warning" -EventType "stage_completed" -Stage "answer" -Message "Model workers completed with API warnings."
```

After clean classification writes completed, add:

```powershell
  Write-OpsEvent -RunRootPath $root -Level "info" -EventType "stage_completed" -Stage "answer" -Message "All model workers completed."
```

When `SkipMerge` exits, add before `exit 0`:

```powershell
  Write-OpsEvent -RunRootPath $root -Level "info" -EventType "run_completed" -Stage "merge" -Message "Run completed without merge because SkipMerge was set."
  Write-OpsSummary -RunRootPath $root
```

After report completion, add:

```powershell
Write-OpsEvent -RunRootPath $root -Level "info" -EventType "run_completed" -Stage "report" -Message "Merged report available."
Write-OpsSummary -RunRootPath $root
```

- [ ] **Step 5: Run PowerShell runner tests**

Run:

```powershell
pytest tests\test_full_api_parallel_with_watch.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add scripts/run_full_api_parallel_with_watch.ps1 tests/test_full_api_parallel_with_watch.py
git commit -m "feat: log parallel runner operations"
```

---

### Task 7: Run Monitor Summary Preference

**Files:**
- Modify: `scripts/ui_app/run_monitor.py`
- Modify: `scripts/ui_app/server.py`
- Modify: `tests/test_ui_run_monitor.py`

- [ ] **Step 1: Write failing monitor tests**

Append to `tests/test_ui_run_monitor.py`:

```python
def test_summarize_parallel_run_prefers_ops_summary_health(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "parallel" / "20260526_120000"
    run_root.mkdir(parents=True)
    (run_root / "ops_summary.json").write_text(
        json.dumps(
            {
                "status": "warning",
                "run_root": str(run_root),
                "current_stage": "answer",
                "updated_at": "2026-05-26T00:00:00Z",
                "issues": ["Ops summary issue"],
                "recommended_actions": ["Ops summary action"],
                "key_files": {"ops_events": "ops_events.jsonl"},
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_parallel_run(run_root, target_brand="AlphaXXXX")

    assert summary["health"]["status"] == "warning"
    assert summary["health"]["source"] == "ops_summary"
    assert summary["health"]["issues"] == ["Ops summary issue"]
    assert summary["health"]["recommended_actions"] == ["Ops summary action"]


def test_ui_server_renders_recommended_actions_from_monitor_health() -> None:
    html = Path("scripts/ui_app/server.py").read_text(encoding="utf-8")

    assert "recommended_actions" in html
    assert "recommended actions" in html.lower()
```

- [ ] **Step 2: Run focused failing monitor tests**

Run:

```powershell
pytest tests\test_ui_run_monitor.py::test_summarize_parallel_run_prefers_ops_summary_health tests\test_ui_run_monitor.py::test_ui_server_renders_recommended_actions_from_monitor_health -q
```

Expected: FAIL because the monitor does not read `ops_summary.json`.

- [ ] **Step 3: Load ops summary in run monitor**

Modify `scripts/ui_app/run_monitor.py` imports:

```python
from scripts.ops_logging import read_summary
```

Near the end of `summarize_parallel_run`, after `health = _build_health(pipeline, models)`, add:

```python
    ops_summary = read_summary(root)
    if ops_summary:
        health = {
            "status": str(ops_summary.get("status") or health.get("status") or "unknown"),
            "issues": [str(item) for item in ops_summary.get("issues") or []],
            "recommended_actions": [str(item) for item in ops_summary.get("recommended_actions") or []],
            "source": "ops_summary",
            "key_files": ops_summary.get("key_files") if isinstance(ops_summary.get("key_files"), dict) else {},
        }
```

Keep the existing `current_stage` logic unchanged so current monitor progress still comes from live facts. Do not generate a summary automatically from the UI read path.

- [ ] **Step 4: Render recommended actions in server health text**

In `scripts/ui_app/server.py`, replace:

```javascript
      const healthLines = [`# chain health`, `status: ${health.status}`].concat((health.issues || []).map((issue) => `- ${issue}`));
```

with:

```javascript
      const healthLines = [`# chain health`, `status: ${health.status}`]
        .concat((health.issues || []).map((issue) => `- ${issue}`))
        .concat((health.recommended_actions || []).length ? [``, `# recommended actions`] : [])
        .concat((health.recommended_actions || []).map((action) => `- ${action}`));
```

- [ ] **Step 5: Run monitor tests**

Run:

```powershell
pytest tests\test_ui_run_monitor.py tests\test_ui_dashboard.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add scripts/ui_app/run_monitor.py scripts/ui_app/server.py tests/test_ui_run_monitor.py
git commit -m "feat: show ops summaries in run monitor"
```

---

### Task 8: Documentation and Verification

**Files:**
- Modify: `docs/ui-console.md`
- Modify: `docs/architecture.md`
- Modify: `docs/risks.md`
- Modify: `docs/next.md`

- [ ] **Step 1: Update UI console docs**

In `docs/ui-console.md`, add under Current Capabilities:

```markdown
- Shows local operations summaries from `ops_summary.json` when present, including health status, issues, recommended actions, and key files.
- Preserves detailed troubleshooting through `ops_events.jsonl`, pipeline log tails, worker log tails, and API attempt files under the selected run root.
```

Add a new short section:

```markdown
## Local Operations Logs

Each monitored run root may contain:

- `ops_events.jsonl`: structured operations events such as run start, stage failure, API failure, worker failure, and summary generation.
- `ops_summary.json`: current local health summary with issues, recommended actions, and key files.

Useful commands:

```powershell
python scripts\ops_logs.py summary --run-root runs\full_api_parallel_ui\<timestamp>
python scripts\ops_logs.py events --run-root runs\full_api_parallel_ui\<timestamp> --level error
python scripts\ops_logs.py doctor --run-root runs\full_api_parallel_ui\<timestamp>
```
```

- [ ] **Step 2: Update architecture docs**

In `docs/architecture.md`, add module bullets:

```markdown
- `scripts/ops_logging.py`: writes structured local operations events and generates `ops_summary.json` from existing run facts without changing benchmark outputs.
- `scripts/ops_logs.py`: CLI for recording runner events, printing summaries, filtering operations events, and regenerating local diagnostics.
```

Add a dependency note:

```markdown
- Local operations logging is additive. The authoritative facts remain pipeline state, worker exit files, API attempts, API events, and output artifacts; operations summaries only interpret those facts for maintenance.
```

- [ ] **Step 3: Update risks docs**

In `docs/risks.md`, add under Operational Risks:

```markdown
- `ops_summary.json` is an interpretation layer, not a source of benchmark truth. If it conflicts with output rows or pipeline state, inspect the underlying files before making decisions.
- Local operations logs are stored inside run roots. Deleting an old run root deletes its troubleshooting history, so important reports should be archived before cleanup.
```

- [ ] **Step 4: Update next-step memory**

At the top of `docs/next.md` under Done, add:

```markdown
- Added local operations logging for run roots: `ops_events.jsonl`, `ops_summary.json`, CLI inspection through `scripts/ops_logs.py`, pipeline-step events, API failure events, parallel-run lifecycle hooks, and Run Monitor summary preference.
```

Under Learned, add:

```markdown
- Local operations summaries work best as an additive interpretation layer over existing facts; they should not replace `pipeline_state.jsonl`, API attempt files, worker exit files, or output CSVs.
```

Under Risks, add:

```markdown
- Operations summaries can become stale if files are manually edited after a run; use `python scripts\ops_logs.py doctor --run-root <run>` to refresh the local diagnosis.
```

Under Next, add:

```markdown
- Add dry-run cleanup reporting for old run roots once operations summaries have been stable across several real runs.
```

- [ ] **Step 5: Run focused and full verification**

Run:

```powershell
pytest tests\test_ops_logging.py tests\test_ops_logs_cli.py tests\test_run_pipeline_step.py tests\test_orchestrator.py tests\test_full_api_parallel_with_watch.py tests\test_ui_run_monitor.py tests\test_ui_dashboard.py -q
```

Expected: PASS.

Then run:

```powershell
pytest -q
```

Expected: PASS.

- [ ] **Step 6: Run a local CLI smoke check**

Run:

```powershell
python scripts\ops_logs.py doctor --run-root runs\full_api_parallel_ui\20260525_214431
```

Expected: prints a status, issues or `none`, recommended actions or `none`, and key files. It writes or refreshes `runs\full_api_parallel_ui\20260525_214431\ops_summary.json`.

- [ ] **Step 7: Commit**

```powershell
git add docs/ui-console.md docs/architecture.md docs/risks.md docs/next.md
git commit -m "docs: document local ops logging"
```

---

## Final Verification

- [ ] Run focused test set:

```powershell
pytest tests\test_ops_logging.py tests\test_ops_logs_cli.py tests\test_run_pipeline_step.py tests\test_orchestrator.py tests\test_full_api_parallel_with_watch.py tests\test_ui_run_monitor.py tests\test_ui_dashboard.py -q
```

Expected: PASS.

- [ ] Run full test suite:

```powershell
pytest -q
```

Expected: PASS.

- [ ] Inspect Git status:

```powershell
git status --short
```

Expected: only intentional files modified or untracked generated run artifacts from the smoke check.

- [ ] If generated smoke files under `runs/` are not meant to be committed, leave them unstaged and mention them in the final handoff.
