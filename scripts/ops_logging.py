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
