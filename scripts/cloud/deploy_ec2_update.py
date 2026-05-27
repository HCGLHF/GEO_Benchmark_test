from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts._common import load_dotenv
from scripts.cloud.defaults import (
    DEFAULT_CORPUS_VERSION,
    DEFAULT_DEPLOY_BRANCH,
    DEFAULT_INDUSTRY_ID,
    DEFAULT_UI_HOST,
    DEFAULT_UI_PORT,
    DEFAULT_UI_SERVICE_NAME,
)

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class DeploymentOptions:
    project_root: Path | str = Path(".")
    branch: str = DEFAULT_DEPLOY_BRANCH
    industry: str = DEFAULT_INDUSTRY_ID
    corpus_version: str = DEFAULT_CORPUS_VERSION
    service_name: str = DEFAULT_UI_SERVICE_NAME
    ui_host: str = DEFAULT_UI_HOST
    ui_port: int = DEFAULT_UI_PORT
    python_executable: str = ""
    execute: bool = False
    log_dir: Path | str | None = None
    timeout_seconds: int = 900
    api_retry_attempts: int = 8
    api_retry_delay_seconds: float = 2.0

    def resolved_root(self) -> Path:
        return Path(self.project_root).resolve()

    def resolved_python(self) -> str:
        if self.python_executable:
            return self.python_executable
        if os.name == "nt":
            return str(self.resolved_root() / ".venv" / "Scripts" / "python.exe")
        return str(self.resolved_root() / ".venv" / "bin" / "python")

    def resolved_log_dir(self) -> Path:
        if self.log_dir is not None:
            return Path(self.log_dir)
        return self.resolved_root() / "runs" / "deployments"


@dataclass(frozen=True)
class DeploymentStep:
    name: str
    command: list[str]
    description: str


def build_deploy_steps(options: DeploymentOptions) -> list[DeploymentStep]:
    python = options.resolved_python()
    return [
        DeploymentStep("git_fetch", ["git", "fetch", "origin"], "Fetch remote branch metadata."),
        DeploymentStep("git_checkout", ["git", "checkout", options.branch], "Switch to the deployment branch."),
        DeploymentStep("git_pull", ["git", "pull", "--ff-only"], "Fast-forward the server checkout."),
        DeploymentStep(
            "install_dependencies",
            [python, "-m", "pip", "install", "-e", ".[dev]"],
            "Install project dependencies into the server virtual environment.",
        ),
        DeploymentStep(
            "hydrate_artifacts",
            [
                python,
                "scripts/cloud/hydrate_artifacts.py",
                "--industry",
                options.industry,
                "--corpus-version",
                options.corpus_version,
                "--run-mode",
                "quick",
                "--run-mode",
                "standard",
                "--project-root",
                ".",
            ],
            "Restore ignored data and report artifacts from cloud storage.",
        ),
        DeploymentStep(
            "verify_cloud_import",
            [
                python,
                "scripts/cloud/verify_cloud_import.py",
                "--industry",
                options.industry,
                "--corpus-version",
                options.corpus_version,
            ],
            "Verify PostgreSQL counts and S3 artifact objects for the active corpus.",
        ),
        DeploymentStep(
            "restart_service",
            ["sudo", "systemctl", "restart", options.service_name],
            "Restart the local UI service.",
        ),
        DeploymentStep(
            "service_health",
            ["systemctl", "is-active", options.service_name],
            "Confirm the UI service is active.",
        ),
        DeploymentStep(
            "api_state",
            ["curl", "-fsS", f"http://{options.ui_host}:{options.ui_port}/api/state"],
            "Confirm the UI API returns current state.",
        ),
    ]


def _now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _parse_json(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _summarize_api_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {}
    corpus = state.get("corpus") or {}
    report = state.get("report") or {}
    return {
        "company_count": corpus.get("company_count"),
        "url_count": corpus.get("url_count"),
        "document_count": corpus.get("document_count"),
        "chunk_count": corpus.get("chunk_count"),
        "latest_report_dir": report.get("report_dir"),
        "target_rank_by_top5": report.get("target_rank_by_top5"),
        "target_top5_share": report.get("target_top5_share"),
        "target_model_mention_rate": report.get("target_model_mention_rate"),
    }


def _write_log(result: dict[str, Any], log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = log_dir / f"{stamp}.json"
    result["log_path"] = str(path)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_deployment(options: DeploymentOptions, *, runner: Runner = subprocess.run) -> dict[str, Any]:
    root = options.resolved_root()
    steps = build_deploy_steps(options)
    started_at = _now_iso()
    result: dict[str, Any] = {
        "status": "dry_run" if not options.execute else "running",
        "branch": options.branch,
        "industry": options.industry,
        "corpus_version": options.corpus_version,
        "project_root": str(root),
        "service_name": options.service_name,
        "ui_url": f"http://{options.ui_host}:{options.ui_port}",
        "started_at": started_at,
        "completed_at": None,
        "steps": [],
        "verification_summary": {},
        "api_state_summary": {},
        "failed_step": None,
        "log_path": None,
    }
    if not options.execute:
        result["steps"] = [
            {"name": step.name, "description": step.description, "command": step.command, "status": "planned"}
            for step in steps
        ]
        return result

    load_dotenv(root / ".env")
    env = os.environ.copy()
    for step in steps:
        step_started = time.monotonic()
        record: dict[str, Any] = {
            "name": step.name,
            "description": step.description,
            "command": step.command,
            "status": "running",
            "attempts": 0,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "duration_seconds": None,
        }
        max_attempts = max(1, options.api_retry_attempts) if step.name == "api_state" else 1
        for attempt in range(1, max_attempts + 1):
            record["attempts"] = attempt
            try:
                completed = runner(
                    step.command,
                    cwd=root,
                    text=True,
                    capture_output=True,
                    timeout=options.timeout_seconds,
                    env=env,
                )
                record["returncode"] = completed.returncode
                record["stdout"] = completed.stdout or ""
                record["stderr"] = completed.stderr or ""
                record["status"] = "completed" if completed.returncode == 0 else "failed"
            except Exception as exc:  # pragma: no cover - subprocess edge path
                record["status"] = "failed"
                record["stderr"] = str(exc)
                record["returncode"] = -1
            if record["status"] == "completed":
                break
            if step.name == "api_state" and attempt < max_attempts and options.api_retry_delay_seconds > 0:
                time.sleep(options.api_retry_delay_seconds)

        record["duration_seconds"] = round(time.monotonic() - step_started, 3)
        result["steps"].append(record)

        parsed = _parse_json(str(record["stdout"]))
        if step.name == "verify_cloud_import" and parsed is not None:
            result["verification_summary"] = parsed
        if step.name == "api_state":
            result["api_state_summary"] = _summarize_api_state(parsed)

        if record["status"] != "completed":
            result["status"] = "failed"
            result["failed_step"] = step.name
            break
    else:
        result["status"] = "completed"

    result["completed_at"] = _now_iso()
    _write_log(result, options.resolved_log_dir())
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Update the EC2 UI checkout, restore cloud artifacts, verify, and restart.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--branch", default=DEFAULT_DEPLOY_BRANCH)
    parser.add_argument("--industry", default=DEFAULT_INDUSTRY_ID)
    parser.add_argument("--corpus-version", default=DEFAULT_CORPUS_VERSION)
    parser.add_argument("--service", default=DEFAULT_UI_SERVICE_NAME)
    parser.add_argument("--host", default=DEFAULT_UI_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_UI_PORT)
    parser.add_argument("--python-executable", default="")
    parser.add_argument("--log-dir", default="")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--api-retry-attempts", type=int, default=8)
    parser.add_argument("--api-retry-delay-seconds", type=float, default=2.0)
    parser.add_argument("--execute", action="store_true", help="Run the update. Without this flag, only print the plan.")
    args = parser.parse_args(argv)

    options = DeploymentOptions(
        project_root=Path(args.project_root),
        branch=args.branch,
        industry=args.industry,
        corpus_version=args.corpus_version,
        service_name=args.service,
        ui_host=args.host,
        ui_port=args.port,
        python_executable=args.python_executable,
        execute=args.execute,
        log_dir=Path(args.log_dir) if args.log_dir else None,
        timeout_seconds=args.timeout_seconds,
        api_retry_attempts=args.api_retry_attempts,
        api_retry_delay_seconds=args.api_retry_delay_seconds,
    )
    result = run_deployment(options)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] in {"dry_run", "completed"} else 1)


if __name__ == "__main__":
    main()
