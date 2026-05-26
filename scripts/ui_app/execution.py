from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.platform_runtime import ProcessHandle, detect_platform
from scripts.pipeline_state import append_event, update_manifest
from scripts.ui_app.run_plan import RunPlanRequest, build_run_plan


PopenFactory = Callable[..., Any]
RunFactory = Callable[..., Any]


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _normalize_slashes(value: str) -> str:
    return value.replace("\\", "/")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _api_command(plan: Any) -> str:
    for command in plan.commands:
        if command.label == "Run full API benchmark in parallel":
            return command.command
    raise ValueError("Run plan does not include a parallel API benchmark command.")


def _command_by_label(plan: Any, command_label: str) -> Any | None:
    return next((command for command in plan.commands if command.label == command_label), None)


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _api_benchmark_command(command: str, platform: str = "auto") -> bool:
    return detect_platform(platform).is_parallel_api_command(command)


def _find_launch_manifest(root: Path, run_root: str) -> tuple[Path, dict[str, Any]] | None:
    target = _normalize_slashes(run_root).rstrip("/")
    launch_root = root / "runs" / "ui_launches"
    if not launch_root.exists():
        return None
    manifests = sorted(
        launch_root.glob("*/launch_manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for manifest_path in manifests:
        payload = _read_json(manifest_path)
        monitor_root = _normalize_slashes(str(payload.get("monitor_run_root") or "")).rstrip("/")
        if monitor_root == target:
            return manifest_path, payload
    return None


def _resolve_run_root(root: Path, run_root: str) -> Path:
    path = Path(run_root)
    return path if path.is_absolute() else root / path


def _update_launch_manifest(path: Path, updates: dict[str, Any]) -> dict[str, Any]:
    payload = _read_json(path)
    payload.update(updates)
    payload["updated_at"] = _utc_now()
    _write_manifest(path, payload)
    return payload


def _launch_process(
    *,
    root: Path,
    command: str,
    platform: str,
    launch_dir: Path,
    log_path: Path,
    manifest_path: Path,
    base_payload: dict[str, Any],
    popen_factory: PopenFactory,
) -> dict[str, Any]:
    launch_dir.mkdir(parents=True, exist_ok=True)
    runtime = detect_platform(platform, popen_factory=popen_factory)
    handle = runtime.launch_shell_command(command, cwd=root, log_path=log_path)

    payload = {
        **base_payload,
        "status": "launched",
        "platform": runtime.platform_id,
        "pid": int(handle.pid),
    }
    if handle.process_group_id is not None:
        payload["process_group_id"] = int(handle.process_group_id)
    _write_manifest(manifest_path, payload)
    payload["manifest_path"] = str(manifest_path)
    return payload


def _preview_stop_command(runtime: Any, handle: ProcessHandle) -> str:
    if runtime.path_style == "windows":
        return f"taskkill /PID {handle.pid} /T /F"
    process_group_id = handle.process_group_id or handle.pid
    return f"kill -- -{process_group_id}"


def stop_guarded_run(
    *,
    project_root: Path | str,
    run_root: str,
    confirmed: bool,
    reason: str = "",
    process_runner: RunFactory = subprocess.run,
    killpg: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    found = _find_launch_manifest(root, run_root)
    if found is None:
        return {"status": "rejected", "error": f"No UI launch manifest found for {run_root}", "monitor_run_root": run_root}
    manifest_path, manifest = found
    command = str(manifest.get("command") or "")
    platform = str(manifest.get("platform") or "windows")
    if not _api_benchmark_command(command, platform):
        return {
            "status": "rejected",
            "error": "Stop is only enabled for guarded API benchmark launches.",
            "monitor_run_root": run_root,
            "manifest_path": str(manifest_path),
        }
    pid = int(manifest.get("pid") or 0)
    if pid <= 0:
        return {"status": "rejected", "error": "Launch manifest does not include a valid pid.", "monitor_run_root": run_root}
    raw_process_group_id = manifest.get("process_group_id")
    process_group_id = int(raw_process_group_id) if raw_process_group_id is not None else None
    runtime_kwargs: dict[str, Any] = {"process_runner": process_runner}
    if killpg is not None:
        runtime_kwargs["killpg"] = killpg
    runtime = detect_platform(platform, **runtime_kwargs)
    handle = ProcessHandle(pid=pid, process_group_id=process_group_id)
    stop_command = _preview_stop_command(runtime, handle)
    base_payload = {
        "status": "confirmation_required",
        "action": "stop",
        "platform": runtime.platform_id,
        "pid": pid,
        "process_group_id": process_group_id,
        "stop_command": stop_command,
        "monitor_run_root": _normalize_slashes(run_root),
        "manifest_path": str(manifest_path),
        "reason": reason,
    }
    if not confirmed:
        return base_payload

    completed = runtime.stop_process_tree(handle)
    return_code = int(completed.return_code)
    status = "stopped" if return_code == 0 else "stop_failed"
    message = reason or "Stopped by user from Run Monitor."
    resolved_run_root = _resolve_run_root(root, run_root)
    append_event(
        resolved_run_root,
        stage="answer",
        status="interrupted" if return_code == 0 else "stop_failed",
        message=message,
        details={"pid": pid, "return_code": return_code, "action": "stop"},
    )
    try:
        update_manifest(resolved_run_root, status="interrupted" if return_code == 0 else "stop_failed")
    except OSError:
        pass
    _update_launch_manifest(
        manifest_path,
        {
            "status": status,
            "stopped_at": _utc_now(),
            "stop_reason": message,
            "stop_command": completed.command,
            "stop_return_code": return_code,
            "stop_stdout": completed.stdout,
            "stop_stderr": completed.stderr,
        },
    )
    return {**base_payload, "status": status, "stop_command": completed.command, "return_code": return_code}


def resume_guarded_run(
    *,
    project_root: Path | str,
    run_root: str,
    confirmed: bool,
    popen_factory: PopenFactory = subprocess.Popen,
    stamp_factory: Callable[[], str] = _stamp,
) -> dict[str, Any]:
    root = Path(project_root)
    found = _find_launch_manifest(root, run_root)
    if found is None:
        return {"status": "rejected", "error": f"No UI launch manifest found for {run_root}", "monitor_run_root": run_root}
    manifest_path, manifest = found
    command = str(manifest.get("command") or "")
    platform = str(manifest.get("platform") or "auto")
    if not _api_benchmark_command(command, platform):
        return {
            "status": "rejected",
            "error": "Resume is only enabled for guarded API benchmark launches.",
            "monitor_run_root": run_root,
            "manifest_path": str(manifest_path),
        }

    stamp = f"{stamp_factory()}_resume"
    launch_dir = root / "runs" / "ui_launches" / stamp
    log_path = launch_dir / "launch.log"
    resume_manifest_path = launch_dir / "launch_manifest.json"
    base_payload = {
        "status": "confirmation_required",
        "action": "resume",
        "command": command,
        "platform": platform,
        "launch_dir": str(launch_dir),
        "log_path": str(log_path),
        "monitor_run_root": _normalize_slashes(run_root),
        "run_stamp": stamp,
        "resumed_from_manifest": str(manifest_path),
    }
    if not confirmed:
        return base_payload

    resolved_run_root = _resolve_run_root(root, run_root)
    append_event(
        resolved_run_root,
        stage="answer",
        status="running",
        message="Resume launched from Run Monitor; existing output rows will be reused.",
        details={"action": "resume", "resumed_from_manifest": str(manifest_path)},
    )
    try:
        update_manifest(resolved_run_root, status="running")
    except OSError:
        pass
    return _launch_process(
        root=root,
        command=command,
        platform=platform,
        launch_dir=launch_dir,
        log_path=log_path,
        manifest_path=resume_manifest_path,
        base_payload=base_payload,
        popen_factory=popen_factory,
    )


def launch_guarded_run(
    *,
    project_root: Path | str,
    request: RunPlanRequest,
    confirmed: bool,
    popen_factory: PopenFactory = subprocess.Popen,
    stamp_factory: Callable[[], str] = _stamp,
) -> dict[str, Any]:
    root = Path(project_root)
    stamp = stamp_factory()
    materialized = replace(
        request,
        pipeline_run_root=request.pipeline_run_root.replace("<timestamp>", stamp),
        run_stamp=stamp,
    )
    plan = build_run_plan(materialized)
    command = _api_command(plan)
    api_parent = Path(materialized.api_run_root)
    monitor_run_root = api_parent / stamp
    launch_dir = root / "runs" / "ui_launches" / stamp
    log_path = launch_dir / "launch.log"
    manifest_path = launch_dir / "launch_manifest.json"

    base_payload = {
        "status": "confirmation_required",
        "command": command,
        "launch_dir": str(launch_dir),
        "log_path": str(log_path),
        "monitor_run_root": _normalize_slashes(str(monitor_run_root)),
        "run_stamp": stamp,
    }
    if not confirmed:
        return base_payload

    return _launch_process(
        root=root,
        command=command,
        platform=materialized.platform,
        launch_dir=launch_dir,
        log_path=log_path,
        manifest_path=manifest_path,
        base_payload=base_payload,
        popen_factory=popen_factory,
    )


def launch_guarded_stage(
    *,
    project_root: Path | str,
    request: RunPlanRequest,
    command_label: str,
    confirmed: bool,
    popen_factory: PopenFactory = subprocess.Popen,
    stamp_factory: Callable[[], str] = _stamp,
) -> dict[str, Any]:
    root = Path(project_root)
    stamp = stamp_factory()
    pipeline_run_root = request.pipeline_run_root
    if "<timestamp>" in pipeline_run_root:
        pipeline_run_root = pipeline_run_root.replace("<timestamp>", stamp)
    elif pipeline_run_root == "<run-root>":
        pipeline_run_root = f"runs/ui_pipeline/{stamp}"
    materialized = replace(request, pipeline_run_root=pipeline_run_root, run_stamp=stamp)
    plan = build_run_plan(materialized)
    planned = _command_by_label(plan, command_label)
    if planned is None:
        return {"status": "rejected", "error": f"Unknown command label: {command_label}", "command_label": command_label}

    command = str(planned.command)
    runtime = detect_platform(materialized.platform, popen_factory=popen_factory)
    if not runtime.is_guarded_pipeline_command(command):
        return {
            "status": "rejected",
            "error": f"{command_label} is not a guarded pipeline step.",
            "command_label": command_label,
            "command": command,
        }

    launch_dir = root / "runs" / "ui_launches" / f"{stamp}_{command_label.replace(' ', '_')}"
    log_path = launch_dir / "launch.log"
    manifest_path = launch_dir / "launch_manifest.json"
    base_payload = {
        "status": "confirmation_required",
        "command_label": command_label,
        "command": command,
        "platform": runtime.platform_id,
        "launch_dir": str(launch_dir),
        "log_path": str(log_path),
        "monitor_run_root": _normalize_slashes(pipeline_run_root),
        "run_stamp": stamp,
    }
    if not confirmed:
        return base_payload
    return _launch_process(
        root=root,
        command=command,
        platform=materialized.platform,
        launch_dir=launch_dir,
        log_path=log_path,
        manifest_path=manifest_path,
        base_payload=base_payload,
        popen_factory=popen_factory,
    )
