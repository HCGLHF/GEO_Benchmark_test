import json
from pathlib import Path

from scripts.ui_app.deployment_action import handle_server_update_request, read_server_update_lock, start_server_update


class FakeProcess:
    def __init__(self, pid: int = 9191):
        self.pid = pid


def test_start_server_update_requires_confirmation_and_previews_fixed_workflow(tmp_path: Path) -> None:
    launches = []

    result = start_server_update(
        project_root=tmp_path,
        confirmed=False,
        popen_factory=lambda *args, **kwargs: launches.append((args, kwargs)) or FakeProcess(),
    )

    assert result["status"] == "confirmation_required"
    assert result["action"] == "server_update"
    assert result["confirmation_message"]
    assert "git pull" in result["confirmation_message"]
    assert "hydrate" in result["confirmation_message"]
    assert "verify" in result["confirmation_message"]
    assert "restart" in result["confirmation_message"]
    assert "scripts/ui_app/run_deployment_update.py" in " ".join(result["command"])
    assert launches == []


def test_start_server_update_launches_fixed_runner_and_writes_lock(tmp_path: Path) -> None:
    launches = []

    def fake_popen(*args, **kwargs):
        launches.append((args, kwargs))
        return FakeProcess(pid=8181)

    result = start_server_update(
        project_root=tmp_path,
        confirmed=True,
        popen_factory=fake_popen,
        stamp_factory=lambda: "20260527_220000",
        launcher_checker=lambda command: (True, ""),
    )

    assert result["status"] == "launched"
    assert result["pid"] == 8181
    assert result["lock_path"].endswith("server_update.lock")
    assert "scripts/ui_app/run_deployment_update.py" in " ".join(launches[0][0][0])
    assert "--execute" not in launches[0][0][0]
    lock_data = json.loads(Path(result["lock_path"]).read_text(encoding="utf-8"))
    assert lock_data["status"] == "running"
    assert lock_data["launcher_pid"] == 8181
    if launches[0][0][0][0] == "systemd-run":
        assert lock_data["pid"] is None
    else:
        assert lock_data["pid"] == 8181
    assert "rm -rf" not in json.dumps(lock_data)


def test_start_server_update_returns_manual_required_when_launcher_unavailable(tmp_path: Path) -> None:
    launches = []

    result = start_server_update(
        project_root=tmp_path,
        confirmed=True,
        popen_factory=lambda *args, **kwargs: launches.append((args, kwargs)) or FakeProcess(),
        launcher_checker=lambda command: (False, "systemd user launcher unavailable: No medium found"),
    )

    assert result["status"] == "manual_required"
    assert "manual command" in result["message"].lower()
    assert "systemd user launcher unavailable" in result["launcher_reason"]
    assert "scripts/cloud/deploy_ec2_update.py" in " ".join(result["manual_command"])
    assert launches == []
    assert not Path(result["lock_path"]).exists()


def test_handle_server_update_request_ignores_browser_command_params(tmp_path: Path) -> None:
    launches = []

    def fake_popen(*args, **kwargs):
        launches.append((args, kwargs))
        return FakeProcess(pid=7171)

    result = handle_server_update_request(
        project_root=tmp_path,
        params={
            "confirmed": ["1"],
            "command": ["rm -rf /"],
            "branch": ["malicious"],
            "service": ["other.service"],
        },
        popen_factory=fake_popen,
        stamp_factory=lambda: "20260527_221000",
        launcher_checker=lambda command: (True, ""),
    )

    command = launches[0][0][0]
    assert result["status"] == "launched"
    assert "rm -rf /" not in command
    assert "malicious" not in command
    assert "other.service" not in command
    assert "scripts/ui_app/run_deployment_update.py" in " ".join(command)


def test_start_server_update_returns_busy_when_existing_lock_is_running(tmp_path: Path) -> None:
    lock = tmp_path / "runs" / "deployments" / "server_update.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps({"status": "running", "pid": 1234, "started_at": "2026-05-27T22:00:00Z"}),
        encoding="utf-8",
    )

    result = start_server_update(
        project_root=tmp_path,
        confirmed=True,
        popen_factory=lambda *args, **kwargs: FakeProcess(),
        pid_is_running=lambda pid: pid == 1234,
    )

    assert result["status"] == "busy"
    assert result["pid"] == 1234
    assert result["lock_path"] == str(lock)


def test_read_server_update_lock_marks_old_pidless_lock_stale(tmp_path: Path) -> None:
    lock = tmp_path / "runs" / "deployments" / "server_update.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps({"status": "running", "pid": None, "started_at": "2026-05-27T00:00:00Z"}),
        encoding="utf-8",
    )

    state = read_server_update_lock(tmp_path)

    assert state["busy"] is False
    assert state["stale"] is True
    assert state["status"] == "stale"
