from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cloud.deploy_ec2_update import DeploymentOptions, run_deployment


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _mark_lock_started(lock_path: Path) -> None:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    payload.update({"status": "running", "pid": os.getpid(), "updated_at": _utc_now()})
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the fixed UI-triggered EC2 deployment update.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--lock-path", required=True)
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    lock_path = Path(args.lock_path)
    _mark_lock_started(lock_path)
    try:
        result = run_deployment(
            DeploymentOptions(
                project_root=project_root,
                execute=True,
                python_executable=sys.executable,
            )
        )
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 0 if result.get("status") == "completed" else 1
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
