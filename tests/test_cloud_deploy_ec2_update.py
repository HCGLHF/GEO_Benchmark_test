import json
import subprocess
from pathlib import Path

from scripts.cloud.deploy_ec2_update import DeploymentOptions, build_deploy_steps, run_deployment


def _completed(command: list[str], returncode: int = 0, stdout: str = "ok", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)


def test_build_deploy_steps_hydrates_and_verifies_current_corpus(tmp_path: Path) -> None:
    options = DeploymentOptions(
        project_root=tmp_path,
        branch="codex/local-ops-logging",
        industry="geo-agency",
        corpus_version="2026-05-27-alpha-refresh",
        service_name="resourcepool-ui.service",
        ui_port=8765,
        python_executable="/opt/resourcepool/Resourcepool_Gen/.venv/bin/python",
    )

    steps = build_deploy_steps(options)

    assert [step.name for step in steps] == [
        "git_fetch",
        "git_checkout",
        "git_pull",
        "install_dependencies",
        "hydrate_artifacts",
        "verify_cloud_import",
        "restart_service",
        "service_health",
        "api_state",
    ]
    hydrate = next(step for step in steps if step.name == "hydrate_artifacts")
    assert hydrate.command == [
        "/opt/resourcepool/Resourcepool_Gen/.venv/bin/python",
        "scripts/cloud/hydrate_artifacts.py",
        "--industry",
        "geo-agency",
        "--corpus-version",
        "2026-05-27-alpha-refresh",
        "--run-mode",
        "quick",
        "--run-mode",
        "standard",
        "--project-root",
        ".",
    ]
    verify = next(step for step in steps if step.name == "verify_cloud_import")
    assert verify.command[-4:] == ["--industry", "geo-agency", "--corpus-version", "2026-05-27-alpha-refresh"]


def test_run_deployment_stops_on_failed_step_and_writes_log(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(command: list[str], **_: object) -> subprocess.CompletedProcess:
        calls.append(command)
        if any(part.endswith("verify_cloud_import.py") for part in command):
            return _completed(command, returncode=1, stdout=json.dumps({"ok": False, "failures": ["artifact missing"]}))
        return _completed(command)

    result = run_deployment(
        DeploymentOptions(
            project_root=tmp_path,
            execute=True,
            log_dir=tmp_path / "runs" / "deployments",
            python_executable="python",
        ),
        runner=fake_runner,
    )

    assert result["status"] == "failed"
    assert result["failed_step"] == "verify_cloud_import"
    assert not any(command[:3] == ["sudo", "systemctl", "restart"] for command in calls)
    log_path = Path(result["log_path"])
    assert log_path.exists()
    logged = json.loads(log_path.read_text(encoding="utf-8"))
    assert logged["status"] == "failed"
    assert logged["verification_summary"]["ok"] is False


def test_run_deployment_records_verifier_and_api_state_summary(tmp_path: Path) -> None:
    def fake_runner(command: list[str], **_: object) -> subprocess.CompletedProcess:
        if any(part.endswith("verify_cloud_import.py") for part in command):
            return _completed(
                command,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "expected_counts": {
                            "inventory_rows": 1683,
                            "documents": 1705,
                            "chunks": 6283,
                            "artifacts": 51,
                        },
                        "failures": [],
                    }
                ),
            )
        if command and command[0] == "curl":
            return _completed(
                command,
                stdout=json.dumps(
                    {
                        "corpus": {"document_count": 1705, "chunk_count": 6283},
                        "report": {"report_dir": "runs/cloud_synced/quick/20260526_002837/merged"},
                    }
                ),
            )
        return _completed(command)

    result = run_deployment(
        DeploymentOptions(
            project_root=tmp_path,
            execute=True,
            log_dir=tmp_path / "runs" / "deployments",
            python_executable="python",
        ),
        runner=fake_runner,
    )

    assert result["status"] == "completed"
    assert result["verification_summary"]["ok"] is True
    assert result["verification_summary"]["expected_counts"]["artifacts"] == 51
    assert result["api_state_summary"]["document_count"] == 1705
    assert result["api_state_summary"]["latest_report_dir"].endswith("20260526_002837/merged")
