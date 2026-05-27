from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts._common import load_dotenv
from scripts.ui_app.config_summary import load_project_options
from scripts.ui_app.corpus_summary import summarize_local_corpus
from scripts.ui_app.deployment_status import summarize_deployment_status
from scripts.ui_app.report_history import list_report_history
from scripts.ui_app.report_summary import summarize_latest_report


TERMINAL_MONITOR_STATUSES = {"failed", "rejected", "stopped", "stop_failed", "interrupted"}


def _database_host_from_url(database_url: str | None) -> str | None:
    if not database_url:
        return None
    parsed = urlparse(database_url)
    return parsed.hostname


def _database_has_password(database_url: str | None) -> bool:
    if not database_url:
        return False
    parsed = urlparse(database_url)
    return bool(parsed.password)


def _cloud_status(project_root: Path) -> dict[str, Any]:
    load_dotenv(project_root / ".env")
    database_url = os.environ.get("DATABASE_URL")
    return {
        "bucket": os.environ.get("GEO_S3_BUCKET") or os.environ.get("S3_BUCKET"),
        "rds_endpoint": os.environ.get("GEO_POSTGRES_HOST") or _database_host_from_url(database_url),
        "aws_region": os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
        "has_aws_access_key": bool(os.environ.get("AWS_ACCESS_KEY_ID")),
        "has_postgres_password": bool(os.environ.get("GEO_POSTGRES_PASSWORD")) or _database_has_password(database_url),
    }


def _resolve_monitor_root(project_root: Path, monitor_root: str) -> Path:
    path = Path(monitor_root)
    if path.is_absolute():
        return path
    return project_root / path


def _monitor_root_is_auto_restorable(project_root: Path, launch_data: dict[str, Any], monitor_root: str) -> bool:
    launch_status = str(launch_data.get("status") or "").strip().lower()
    if launch_status in TERMINAL_MONITOR_STATUSES:
        return False

    manifest_path = _resolve_monitor_root(project_root, monitor_root) / "run_manifest.json"
    try:
        run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True

    run_status = str(run_manifest.get("status") or "").strip().lower()
    return run_status not in TERMINAL_MONITOR_STATUSES


def _latest_monitor_run_root(project_root: Path) -> str:
    launch_dir = project_root / "runs" / "ui_launches"
    if not launch_dir.exists():
        return ""
    candidates = sorted(
        launch_dir.rglob("launch_manifest.json"),
        key=lambda path: (path.stat().st_mtime, path.parent.name),
        reverse=True,
    )
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        monitor_root = str(data.get("monitor_run_root") or "").strip()
        if monitor_root and _monitor_root_is_auto_restorable(project_root, data, monitor_root):
            return monitor_root
    return ""


def build_dashboard_state(project_root: Path | str = Path(".")) -> dict[str, Any]:
    root = Path(project_root)
    options = load_project_options(root)
    return {
        "project_root": str(root.resolve()),
        "corpus": summarize_local_corpus(root).to_dict(),
        "options": options.to_dict(),
        "report": summarize_latest_report(root, target_brand=options.target_brand).to_dict(),
        "report_history": [item.to_dict() for item in list_report_history(root, target_brand=options.target_brand, limit=10)],
        "latest_monitor_run_root": _latest_monitor_run_root(root),
        "cloud": _cloud_status(root),
        "deployment": summarize_deployment_status(root),
    }
