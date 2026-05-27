from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PopenFactory = Callable[..., Any]
PidChecker = Callable[[int], bool]
LauncherChecker = Callable[[list[str]], tuple[bool, str]]

CONFIRMATION_MESSAGE = (
    "Run the fixed server update workflow? This will git pull, hydrate artifacts, "
    "verify cloud import, restart service, and check /api/state."
)
MANUAL_REQUIRED_MESSAGE = (
    "Server-side execution is not enabled from this UI process. Run the fixed "
    "manual command on the server, then refresh this page for the latest log."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _deploy_dir(project_root: Path | str) -> Path:
    return Path(project_root) / "runs" / "deployments"


def server_update_lock_path(project_root: Path | str) -> Path:
    return _deploy_dir(project_root) / "server_update.lock"


def _default_pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _lock_without_pid_is_busy(started_at: Any) -> bool:
    if not started_at:
        return True
    try:
        parsed = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() < 60


def read_server_update_lock(
    project_root: Path | str,
    *,
    pid_is_running: PidChecker = _default_pid_is_running,
) -> dict[str, Any]:
    path = server_update_lock_path(project_root)
    if not path.exists():
        return {"busy": False, "lock_path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"busy": True, "status": "running", "lock_path": str(path)}
    pid = int(payload.get("pid") or 0)
    running_status = str(payload.get("status") or "").lower() == "running"
    busy = running_status and (_lock_without_pid_is_busy(payload.get("started_at")) if pid <= 0 else pid_is_running(pid))
    stale = running_status and not busy
    return {
        "busy": busy,
        "status": "stale" if stale else payload.get("status", "running"),
        "stale": stale,
        "pid": pid or None,
        "started_at": payload.get("started_at"),
        "lock_path": str(path),
    }


def _child_update_command(project_root: Path) -> list[str]:
    return [
        sys.executable,
        "scripts/ui_app/run_deployment_update.py",
        "--project-root",
        str(project_root),
        "--lock-path",
        str(server_update_lock_path(project_root)),
    ]


def _fixed_update_command(project_root: Path, stamp: str) -> list[str]:
    child_command = _child_update_command(project_root)
    if os.name == "nt":
        return child_command
    return [
        "systemd-run",
        "--user",
        "--collect",
        f"--unit=resourcepool-ui-update-{stamp}",
        f"--working-directory={project_root}",
        *child_command,
    ]


def _manual_update_command(project_root: Path) -> list[str]:
    python = (
        str(project_root / ".venv" / "Scripts" / "python.exe")
        if os.name == "nt"
        else str(project_root / ".venv" / "bin" / "python")
    )
    return [
        python,
        "scripts/cloud/deploy_ec2_update.py",
        "--project-root",
        str(project_root),
        "--python-executable",
        python,
        "--execute",
    ]


def _uses_systemd_run(command: list[str]) -> bool:
    return bool(command) and command[0] == "systemd-run"


def _first_log_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:240]
    return ""


def _default_launcher_is_available(command: list[str]) -> tuple[bool, str]:
    if not _uses_systemd_run(command):
        return True, ""
    try:
        completed = subprocess.run(
            ["systemctl", "--user", "list-units", "--no-pager"],
            text=True,
            capture_output=True,
            timeout=5,
        )
    except Exception as exc:  # pragma: no cover - platform edge path
        return False, f"Unable to check systemd user launcher: {exc}"
    if completed.returncode == 0:
        return True, ""
    reason = _first_log_line(completed.stderr) or _first_log_line(completed.stdout)
    return False, f"systemd user launcher unavailable: {reason or 'non-zero exit'}"


def start_server_update(
    *,
    project_root: Path | str,
    confirmed: bool,
    popen_factory: PopenFactory = subprocess.Popen,
    stamp_factory: Callable[[], str] = _stamp,
    pid_is_running: PidChecker = _default_pid_is_running,
    launcher_checker: LauncherChecker = _default_launcher_is_available,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    lock_state = read_server_update_lock(root, pid_is_running=pid_is_running)
    stamp = stamp_factory()
    command = _fixed_update_command(root, stamp)
    base_payload = {
        "status": "confirmation_required",
        "action": "server_update",
        "confirmation_message": CONFIRMATION_MESSAGE,
        "command": command,
        "manual_command": _manual_update_command(root),
        "lock_path": str(server_update_lock_path(root)),
    }
    if lock_state.get("busy"):
        return {
            **base_payload,
            "status": "busy",
            "pid": lock_state.get("pid"),
            "started_at": lock_state.get("started_at"),
        }
    if not confirmed:
        return base_payload

    launcher_available, launcher_reason = launcher_checker(command)
    if not launcher_available:
        return {
            **base_payload,
            "status": "manual_required",
            "message": MANUAL_REQUIRED_MESSAGE,
            "launcher_reason": launcher_reason,
        }

    deploy_dir = _deploy_dir(root)
    deploy_dir.mkdir(parents=True, exist_ok=True)
    launcher_log_path = deploy_dir / f"server_update_{stamp}.log"
    lock_path = server_update_lock_path(root)
    lock_payload = {
        "status": "running",
        "action": "server_update",
        "started_at": _utc_now(),
        "command": command,
        "launcher_log_path": str(launcher_log_path),
        "pid": None,
    }
    lock_path.write_text(json.dumps(lock_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    log_handle = launcher_log_path.open("ab")
    try:
        kwargs: dict[str, Any] = {
            "cwd": root,
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
        }
        if os.name != "nt":
            kwargs["start_new_session"] = True
        process = popen_factory(command, **kwargs)
    finally:
        log_handle.close()

    pid = int(getattr(process, "pid", 0) or 0)
    lock_payload["launcher_pid"] = pid
    if not _uses_systemd_run(command):
        lock_payload["pid"] = pid
    lock_payload["updated_at"] = _utc_now()
    lock_path.write_text(json.dumps(lock_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        **base_payload,
        "status": "launched",
        "pid": pid,
        "launcher_log_path": str(launcher_log_path),
    }


def handle_server_update_request(
    *,
    project_root: Path | str,
    params: dict[str, list[str]],
    popen_factory: PopenFactory = subprocess.Popen,
    stamp_factory: Callable[[], str] = _stamp,
    pid_is_running: PidChecker = _default_pid_is_running,
    launcher_checker: LauncherChecker = _default_launcher_is_available,
) -> dict[str, Any]:
    confirmed = params.get("confirmed", ["0"])[0] == "1"
    return start_server_update(
        project_root=project_root,
        confirmed=confirmed,
        popen_factory=popen_factory,
        stamp_factory=stamp_factory,
        pid_is_running=pid_is_running,
        launcher_checker=launcher_checker,
    )
