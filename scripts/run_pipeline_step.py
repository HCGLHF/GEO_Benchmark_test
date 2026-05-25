from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ops_logging import safe_write_event
from scripts.pipeline_state import append_event


def safe_log_name(stage: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stage).strip("_") or "step"


def run_step(run_root: Path, stage: str, command: list[str], model: str = "") -> int:
    if not command:
        raise ValueError("Command is required after --")
    log_dir = run_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{safe_log_name(stage)}.log"
    append_event(
        run_root,
        stage=stage,
        status="running",
        message=f"Started: {' '.join(command)}",
        model=model or None,
        details={"log_path": str(log_path)},
    )
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
    with log_path.open("a", encoding="utf-8", errors="replace") as log:
        process = subprocess.run(command, text=True, stdout=log, stderr=subprocess.STDOUT, check=False)
    status = "completed" if process.returncode == 0 else "failed"
    append_event(
        run_root,
        stage=stage,
        status=status,
        message=f"Finished with exit code {process.returncode}",
        model=model or None,
        details={"exit_code": process.returncode, "log_path": str(log_path)},
    )
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
    return process.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one pipeline command and record pipeline_state.jsonl events.")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    raise SystemExit(run_step(Path(args.run_root), args.stage, command, model=args.model))


if __name__ == "__main__":
    main()
