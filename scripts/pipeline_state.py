from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_NAME = "run_manifest.json"
STATE_NAME = "pipeline_state.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def initialize_manifest(
    *,
    run_root: Path | str,
    run_type: str,
    stages: list[str],
    models: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    status: str = "running",
) -> dict[str, Any]:
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_type": run_type,
        "status": status,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "stages": stages,
        "models": models or [],
        "metadata": metadata or {},
    }
    (root / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def update_manifest(run_root: Path | str, **updates: Any) -> dict[str, Any]:
    root = Path(run_root)
    manifest_path = root / MANIFEST_NAME
    manifest = read_manifest(root)
    manifest.update(updates)
    manifest["updated_at"] = utc_now()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def append_event(
    run_root: Path | str,
    *,
    stage: str,
    status: str,
    message: str = "",
    details: dict[str, Any] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    event = {
        "created_at": utc_now(),
        "stage": stage,
        "status": status,
        "message": message,
        "details": details or {},
    }
    if model:
        event["model"] = model
    with (root / STATE_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_manifest(run_root: Path | str) -> dict[str, Any]:
    path = Path(run_root) / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def read_events(run_root: Path | str) -> list[dict[str, Any]]:
    path = Path(run_root) / STATE_NAME
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def read_pipeline_status(run_root: Path | str) -> dict[str, Any]:
    manifest = read_manifest(run_root)
    events = read_events(run_root)
    stages: dict[str, dict[str, Any]] = {}
    for stage in manifest.get("stages", []) or []:
        stages[str(stage)] = {"status": "pending", "message": "", "details": {}, "updated_at": ""}
    for event in events:
        stage = str(event.get("stage") or "unknown")
        stages[stage] = {
            "status": str(event.get("status") or ""),
            "message": str(event.get("message") or ""),
            "details": event.get("details") if isinstance(event.get("details"), dict) else {},
            "updated_at": str(event.get("created_at") or ""),
            "model": event.get("model", ""),
        }

    current_stage = ""
    if str(stages.get("report", {}).get("status") or "").lower() != "completed":
        for event in reversed(events):
            stage_name = str(event.get("stage") or "")
            status = str(event.get("status") or "").lower()
            latest_stage_status = str(stages.get(stage_name, {}).get("status") or "").lower()
            if status not in {"completed", "skipped"} and latest_stage_status == status:
                current_stage = stage_name
                break
        if not current_stage:
            for stage_name, stage in stages.items():
                if str(stage["status"]).lower() == "pending":
                    current_stage = stage_name
                    break
        if not current_stage:
            for stage_name, stage in stages.items():
                if str(stage["status"]).lower() not in {"completed", "skipped"}:
                    current_stage = stage_name
                    break
    return {
        "manifest": manifest,
        "current_stage": current_stage,
        "stages": stages,
        "events": events,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read and write GEO pipeline state files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--run-root", required=True)
    init_parser.add_argument("--run-type", required=True)
    init_parser.add_argument("--stage", action="append", default=[])
    init_parser.add_argument("--model", action="append", default=[])
    init_parser.add_argument("--metadata-json", default="{}")

    append_parser = subparsers.add_parser("append")
    append_parser.add_argument("--run-root", required=True)
    append_parser.add_argument("--stage", required=True)
    append_parser.add_argument("--status", required=True)
    append_parser.add_argument("--message", default="")
    append_parser.add_argument("--model", default="")
    append_parser.add_argument("--details-json", default="{}")

    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("--run-root", required=True)

    args = parser.parse_args()
    if args.command == "init":
        metadata = json.loads(args.metadata_json)
        result = initialize_manifest(
            run_root=args.run_root,
            run_type=args.run_type,
            stages=args.stage,
            models=args.model,
            metadata=metadata,
        )
    elif args.command == "append":
        details = json.loads(args.details_json)
        result = append_event(
            args.run_root,
            stage=args.stage,
            status=args.status,
            message=args.message,
            model=args.model or None,
            details=details,
        )
    else:
        result = read_pipeline_status(args.run_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
