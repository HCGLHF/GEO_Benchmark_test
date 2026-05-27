from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from scripts.cloud.defaults import DEFAULT_CORPUS_VERSION

GitRunner = Callable[..., subprocess.CompletedProcess]


def _run_git(project_root: Path, command: list[str], git_runner: GitRunner | None) -> str | None:
    runner = git_runner or subprocess.run
    try:
        completed = runner(
            command,
            cwd=project_root,
            text=True,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    value = str(completed.stdout or "").strip()
    return value or None


def _git_status(project_root: Path, git_runner: GitRunner | None) -> dict[str, str | None]:
    return {
        "commit": _run_git(project_root, ["git", "rev-parse", "--short", "HEAD"], git_runner),
        "branch": _run_git(project_root, ["git", "rev-parse", "--abbrev-ref", "HEAD"], git_runner),
    }


def _latest_deploy_log(project_root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    log_dir = project_root / "runs" / "deployments"
    if not log_dir.exists():
        return None, None
    candidates = sorted(log_dir.glob("*.json"), key=lambda path: (path.name, path.stat().st_mtime), reverse=True)
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return path, data
    return None, None


def _verification_summary(log_data: dict[str, Any] | None) -> dict[str, Any]:
    if not log_data:
        return {
            "ok": None,
            "inventory_rows": None,
            "documents": None,
            "chunks": None,
            "artifacts": None,
            "failure_count": None,
        }
    verification = log_data.get("verification_summary") or {}
    counts = verification.get("expected_counts") or {}
    failures = verification.get("failures") or []
    return {
        "ok": verification.get("ok"),
        "inventory_rows": counts.get("inventory_rows"),
        "documents": counts.get("documents"),
        "chunks": counts.get("chunks"),
        "artifacts": counts.get("artifacts"),
        "failure_count": len(failures) if isinstance(failures, list) else None,
    }


def _api_state_summary(log_data: dict[str, Any] | None) -> dict[str, Any]:
    if not log_data:
        return {
            "document_count": None,
            "chunk_count": None,
            "latest_report_dir": None,
        }
    state = log_data.get("api_state_summary") or {}
    return {
        "document_count": state.get("document_count"),
        "chunk_count": state.get("chunk_count"),
        "latest_report_dir": state.get("latest_report_dir"),
        "target_top5_share": state.get("target_top5_share"),
        "target_model_mention_rate": state.get("target_model_mention_rate"),
    }


def summarize_deployment_status(
    project_root: Path | str = Path("."),
    *,
    git_runner: GitRunner | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    log_path, log_data = _latest_deploy_log(root)
    return {
        "git": _git_status(root, git_runner),
        "default_corpus_version": DEFAULT_CORPUS_VERSION,
        "last_deployment": {
            "status": (log_data or {}).get("status", "missing"),
            "branch": (log_data or {}).get("branch"),
            "corpus_version": (log_data or {}).get("corpus_version"),
            "completed_at": (log_data or {}).get("completed_at"),
            "failed_step": (log_data or {}).get("failed_step"),
            "log_path": str(log_path) if log_path else None,
        },
        "cloud_verification": _verification_summary(log_data),
        "api_state": _api_state_summary(log_data),
    }
