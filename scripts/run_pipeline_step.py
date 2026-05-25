from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ops_logging import safe_write_event
from scripts.pipeline_state import append_event


SENSITIVE_COMMAND_KEYS = {
    "api-key",
    "api_key",
    "apikey",
    "authorization",
    "corpus",
    "input",
    "messages",
    "password",
    "prompt",
    "secret",
    "token",
}


def safe_log_name(stage: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stage).strip("_") or "step"


def _sensitive_name(value: str) -> bool:
    normalized = value.strip().lstrip("-").lower()
    return normalized in SENSITIVE_COMMAND_KEYS or any(key in normalized for key in {"api-key", "api_key", "secret", "token"})


def redact_command(command: list[str], max_args: int = 24, max_arg_length: int = 120) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for index, raw_arg in enumerate(command):
        if index >= max_args:
            redacted.append("[truncated]")
            break
        arg = str(raw_arg)
        if redact_next:
            redacted.append("[redacted]")
            redact_next = False
            continue
        if "=" in arg:
            name, _value = arg.split("=", 1)
            if _sensitive_name(name):
                redacted.append(f"{name}=[redacted]")
                continue
        if _sensitive_name(arg):
            redacted.append(arg)
            redact_next = True
            continue
        if len(arg) > max_arg_length:
            redacted.append(arg[: max_arg_length - 3] + "...")
        else:
            redacted.append(arg)
    return redacted


def command_summary(command: list[str]) -> str:
    executable = command[0] if command else "command"
    return f"Started command: {executable} ({len(command)} args)"


def run_step(run_root: Path, stage: str, command: list[str], model: str = "") -> int:
    if not command:
        raise ValueError("Command is required after --")
    log_dir = run_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{safe_log_name(stage)}.log"
    redacted_command = redact_command(command)
    append_event(
        run_root,
        stage=stage,
        status="running",
        message=command_summary(command),
        model=model or None,
        details={"log_path": str(log_path), "command": redacted_command, "command_arg_count": len(command)},
    )
    safe_write_event(
        run_root,
        level="info",
        event_type="stage_started",
        stage=stage,
        model=model,
        message=command_summary(command),
        details={"log_path": str(log_path), "command": redacted_command, "command_arg_count": len(command)},
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
