from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from scripts.ui_app.run_plan import RunPlanRequest, build_run_plan


PopenFactory = Callable[..., Any]


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _normalize_slashes(value: str) -> str:
    return value.replace("\\", "/")


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


def _launch_process(
    *,
    root: Path,
    command: str,
    launch_dir: Path,
    log_path: Path,
    manifest_path: Path,
    base_payload: dict[str, Any],
    popen_factory: PopenFactory,
) -> dict[str, Any]:
    launch_dir.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("a", encoding="utf-8", errors="replace")
    try:
        process = popen_factory(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            cwd=str(root),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
    finally:
        log_handle.close()

    payload = {
        **base_payload,
        "status": "launched",
        "pid": int(process.pid),
    }
    _write_manifest(manifest_path, payload)
    payload["manifest_path"] = str(manifest_path)
    return payload


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
    if not command.startswith("python scripts\\run_pipeline_step.py"):
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
        launch_dir=launch_dir,
        log_path=log_path,
        manifest_path=manifest_path,
        base_payload=base_payload,
        popen_factory=popen_factory,
    )
