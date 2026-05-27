import json
import subprocess
from pathlib import Path

from scripts.ui_app.deployment_status import summarize_deployment_status


def test_summarize_deployment_status_reads_latest_deploy_log(tmp_path: Path) -> None:
    log_dir = tmp_path / "runs" / "deployments"
    log_dir.mkdir(parents=True)
    (log_dir / "20260527_120000.json").write_text(
        json.dumps({"status": "failed", "completed_at": "2026-05-27T12:00:00+08:00"}),
        encoding="utf-8",
    )
    (log_dir / "20260527_130000.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "branch": "codex/local-ops-logging",
                "corpus_version": "2026-05-27-alpha-refresh",
                "completed_at": "2026-05-27T13:00:00+08:00",
                "verification_summary": {
                    "ok": True,
                    "expected_counts": {
                        "inventory_rows": 1683,
                        "documents": 1705,
                        "chunks": 6283,
                        "artifacts": 51,
                    },
                    "failures": [],
                },
                "api_state_summary": {
                    "document_count": 1705,
                    "chunk_count": 6283,
                    "latest_report_dir": "runs/cloud_synced/quick/20260526_002837/merged",
                },
                "steps": [
                    {
                        "name": "git_pull",
                        "description": "Fast-forward the server checkout.",
                        "status": "completed",
                        "attempts": 1,
                        "returncode": 0,
                        "duration_seconds": 0.2,
                        "stdout": "AWS_SECRET_ACCESS_KEY=do-not-render",
                        "stderr": "DATABASE_URL=postgresql://user:secret@example/postgres",
                    },
                    {
                        "name": "verify_cloud_import",
                        "description": "Verify PostgreSQL counts and S3 artifact objects for the active corpus.",
                        "status": "completed",
                        "attempts": 1,
                        "returncode": 0,
                        "duration_seconds": 0.4,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    def fake_git_runner(command: list[str], **_: object) -> subprocess.CompletedProcess:
        if "--short" in command:
            return subprocess.CompletedProcess(command, 0, stdout="af4ddd2\n", stderr="")
        if "--abbrev-ref" in command:
            return subprocess.CompletedProcess(command, 0, stdout="codex/local-ops-logging\n", stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected")

    status = summarize_deployment_status(tmp_path, git_runner=fake_git_runner)

    assert status["git"]["commit"] == "af4ddd2"
    assert status["git"]["branch"] == "codex/local-ops-logging"
    assert status["default_corpus_version"] == "2026-05-27-alpha-refresh"
    assert status["last_deployment"]["status"] == "completed"
    assert status["last_deployment"]["corpus_version"] == "2026-05-27-alpha-refresh"
    assert status["cloud_verification"]["ok"] is True
    assert status["cloud_verification"]["artifacts"] == 51
    assert status["api_state"]["latest_report_dir"].endswith("20260526_002837/merged")
    assert [step["name"] for step in status["deployment_steps"]] == ["git_pull", "verify_cloud_import"]
    assert status["deployment_steps"][0]["attempts"] == 1
    assert status["deployment_steps"][0]["duration_seconds"] == 0.2
    serialized = json.dumps(status, ensure_ascii=False)
    assert "AWS_SECRET_ACCESS_KEY" not in serialized
    assert "DATABASE_URL" not in serialized
    assert "do-not-render" not in serialized


def test_summarize_deployment_status_handles_missing_log_and_git_failure(tmp_path: Path) -> None:
    def failing_git_runner(command: list[str], **_: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(command, 128, stdout="", stderr="not a git repo")

    status = summarize_deployment_status(tmp_path, git_runner=failing_git_runner)

    assert status["git"]["commit"] is None
    assert status["git"]["branch"] is None
    assert status["last_deployment"]["status"] == "missing"
    assert status["cloud_verification"]["ok"] is None
    assert status["deployment_steps"] == []


def test_summarize_deployment_status_marks_failed_step_details(tmp_path: Path) -> None:
    log_dir = tmp_path / "runs" / "deployments"
    log_dir.mkdir(parents=True)
    (log_dir / "20260527_140000.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "completed_at": "2026-05-27T14:00:00+08:00",
                "failed_step": "hydrate_artifacts",
                "steps": [
                    {"name": "git_pull", "status": "completed", "attempts": 1, "returncode": 0},
                    {
                        "name": "hydrate_artifacts",
                        "status": "failed",
                        "attempts": 1,
                        "returncode": 1,
                        "stderr": "permission denied",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    status = summarize_deployment_status(tmp_path, git_runner=lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="x\n", stderr=""))

    assert status["last_deployment"]["status"] == "failed"
    assert status["last_deployment"]["failed_step"] == "hydrate_artifacts"
    failed = next(step for step in status["deployment_steps"] if step["name"] == "hydrate_artifacts")
    assert failed["status"] == "failed"
    assert failed["returncode"] == 1
    assert "permission denied" not in json.dumps(status)
