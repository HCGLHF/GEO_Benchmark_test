from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.full_api_run_status import summarize_run_dir
from scripts.pipeline_state import read_pipeline_status


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


def _relative_to_run(run_root: Path, path: Path) -> str:
    try:
        return path.relative_to(run_root).as_posix()
    except ValueError:
        return str(path)


def _model_dirs(run_root: Path) -> list[Path]:
    excluded = {"cache", "merged", "logs"}
    if not run_root.exists():
        return []
    return sorted(
        child
        for child in run_root.iterdir()
        if child.is_dir() and child.name not in excluded
    )


def _read_exit_code(model_dir: Path) -> str:
    path = model_dir / "worker_exit_code.txt"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _api_summary_files(run_root: Path) -> list[str]:
    merged_summary = run_root / "merged" / "api_call_summary.csv"
    if merged_summary.exists():
        return [_relative_to_run(run_root, merged_summary)]
    root_summary = run_root / "api_call_summary.csv"
    if root_summary.exists():
        return [_relative_to_run(run_root, root_summary)]
    for model_dir in _model_dirs(run_root):
        model_summary = model_dir / "api_call_summary.csv"
        if model_summary.exists():
            return [_relative_to_run(run_root, model_summary)]
    return []


def _append_once(rows: list[str], text: str) -> None:
    value = str(text or "").strip()
    if value and value not in rows:
        rows.append(value)


def _actions_for_text(text: str) -> list[str]:
    value = str(text or "").lower()
    actions: list[str] = []
    if "429" in value or "rate limit" in value or "rate-limit" in value or "too many requests" in value:
        actions.append("Retry with backoff, lower concurrency, or wait for provider rate limits to reset.")
    if "402" in value or "payment required" in value or "payment-required" in value:
        actions.append("Payment required: check provider credits, billing status, and API key access.")
    return actions


def _severity_rank(status: str) -> int:
    return {
        "ok": 0,
        "warning": 1,
        "stalled": 2,
        "error": 3,
    }.get(str(status or "ok"), 0)


def _max_status(*statuses: str) -> str:
    return max((str(status or "ok") for status in statuses), key=_severity_rank, default="ok")


def generate_summary(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    status = "ok"
    issues: list[str] = []
    recommended_actions: list[str] = []
    worker_logs: list[str] = []
    api_summary = _api_summary_files(root)

    pipeline = read_pipeline_status(root)
    current_stage = str(pipeline.get("current_stage") or "")
    manifest = pipeline.get("manifest") if isinstance(pipeline.get("manifest"), dict) else {}
    manifest_status = str(manifest.get("status") or "").lower()
    if manifest_status in {"complete_with_model_warnings", "interrupted"}:
        status = _max_status(status, "warning")
        _append_once(issues, f"Pipeline status is {manifest_status}.")
    elif manifest_status in {"failed", "failure", "error"}:
        status = _max_status(status, "error")
        _append_once(issues, f"Pipeline status is {manifest_status}.")

    stages = pipeline.get("stages") if isinstance(pipeline.get("stages"), dict) else {}
    for stage_name, stage in stages.items():
        if not isinstance(stage, dict):
            continue
        stage_status = str(stage.get("status") or "").lower()
        message = str(stage.get("message") or "").strip()
        if stage_status in {"failed", "failure", "error"}:
            status = _max_status(status, "error")
            _append_once(issues, f"Pipeline stage {stage_name} {stage_status}: {message}".rstrip(": "))
        elif stage_status in {"complete_with_model_warnings", "interrupted"}:
            status = _max_status(status, "warning")
            _append_once(issues, f"Pipeline stage {stage_name} is {stage_status}: {message}".rstrip(": "))

    for model_dir in _model_dirs(root):
        safe_name = model_dir.name
        worker_logs.append(_relative_to_run(root, model_dir / "worker.log"))
        exit_code = _read_exit_code(model_dir)
        try:
            model_summary = summarize_run_dir(model_dir, exit_code or None)
        except Exception as exc:
            status = _max_status(status, "warning")
            _append_once(issues, f"{safe_name} could not be summarized: {exc}")
            continue

        summary_status = str((model_summary.get("summary") or {}).get("status") or "")
        if summary_status == "likely_stalled":
            status = _max_status(status, "stalled")
            _append_once(issues, f"{safe_name} appears likely_stalled.")

        complete_outputs = bool(model_summary.get("complete_outputs"))
        if exit_code and exit_code != "0" and not complete_outputs:
            status = _max_status(status, "error")
            _append_once(issues, f"{safe_name} exited with code {exit_code}.")
        elif bool(model_summary.get("warning")) or summary_status == "complete_with_failures":
            status = _max_status(status, "warning")

        for message in model_summary.get("messages") or []:
            _append_once(issues, str(message))
            for action in _actions_for_text(str(message)):
                _append_once(recommended_actions, action)
        for failure in ((model_summary.get("summary") or {}).get("failures") or []):
            if isinstance(failure, dict):
                error_text = str(failure.get("error") or "")
                for action in _actions_for_text(error_text):
                    _append_once(recommended_actions, action)

    for event in read_events(root):
        level = str(event.get("level") or "").lower()
        if level not in {"warning", "error"}:
            continue
        status = _max_status(status, "error" if level == "error" else "warning")
        message = str(event.get("message") or "").strip()
        event_type = str(event.get("event_type") or "").strip()
        stage = str(event.get("stage") or "").strip()
        model = str(event.get("model") or "").strip()
        parts = [part for part in [event_type, stage, model, message] if part]
        _append_once(issues, ": ".join(parts))
        action_text = " ".join(
            [
                message,
                json.dumps(event.get("details") or {}, ensure_ascii=False, sort_keys=True),
            ]
        )
        for action in _actions_for_text(action_text):
            _append_once(recommended_actions, action)

    return {
        "status": status,
        "run_root": str(run_root),
        "current_stage": current_stage,
        "updated_at": utc_now(),
        "issues": issues,
        "recommended_actions": recommended_actions,
        "key_files": {
            "pipeline_state": "pipeline_state.jsonl",
            "ops_events": EVENTS_NAME,
            "worker_logs": worker_logs,
            "api_summary": api_summary,
        },
    }


def write_summary(run_root: Path | str) -> dict[str, Any]:
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    summary = generate_summary(run_root)
    (root / SUMMARY_NAME).write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    write_event(
        root,
        level="info",
        event_type="summary_generated",
        message=f"Operations summary generated with status {summary['status']}.",
        details={"status": summary["status"]},
        source="ops_logging",
    )
    return summary


def read_summary(run_root: Path | str) -> dict[str, Any]:
    path = Path(run_root) / SUMMARY_NAME
    if not path.exists():
        return {}
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return summary if isinstance(summary, dict) else {}


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
