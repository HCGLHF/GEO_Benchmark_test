from __future__ import annotations

import signal
import subprocess
from pathlib import Path

from scripts.platform_runtime import ProcessHandle, detect_platform, posix_runtime, windows_runtime


class FakeProcess:
    def __init__(self, pid: int = 4242):
        self.pid = pid


class FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "SUCCESS", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeTimeoutThenStoppedProcess:
    def __init__(self) -> None:
        self.wait_calls: list[float] = []

    def wait(self, timeout: float):
        self.wait_calls.append(timeout)
        if len(self.wait_calls) == 1:
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
        return 0


def test_windows_runtime_formats_command_with_windows_paths() -> None:
    runtime = windows_runtime()

    command = runtime.format_command(["python", "scripts\\run_pipeline_step.py", "--stage", "owned site"])

    assert command == 'python scripts\\run_pipeline_step.py --stage "owned site"'
    assert runtime.platform_id == "windows"
    assert runtime.path_style == "windows"


def test_posix_runtime_formats_command_with_shell_quoting() -> None:
    runtime = posix_runtime(platform_id="wsl")

    command = runtime.format_command(["python", "scripts/run_pipeline_step.py", "--stage", "owned site"])

    assert command == "python scripts/run_pipeline_step.py --stage 'owned site'"
    assert runtime.platform_id == "wsl"
    assert runtime.path_style == "posix"


def test_windows_runtime_converts_paths_to_windows_style() -> None:
    runtime = windows_runtime()

    assert runtime.path("scripts/run_pipeline_step.py") == "scripts\\run_pipeline_step.py"


def test_posix_runtime_converts_paths_to_posix_style() -> None:
    runtime = posix_runtime(platform_id="wsl")

    assert runtime.path("scripts\\run_pipeline_step.py") == "scripts/run_pipeline_step.py"


def test_runtime_recognizes_parallel_api_commands() -> None:
    runtime = posix_runtime(platform_id="linux")

    assert runtime.is_parallel_api_command("python scripts/full_api_parallel_runner.py --run-mode test")
    assert runtime.is_parallel_api_command("bash scripts/run_full_api_parallel_with_watch.sh --run-mode test")
    assert runtime.is_parallel_api_command(
        "powershell -ExecutionPolicy Bypass -File scripts\\run_full_api_parallel_with_watch.ps1 -RunMode test"
    )
    assert not runtime.is_parallel_api_command("python scripts/run_pipeline_step.py --run-root runs/x")


def test_runtime_rejects_parallel_api_command_substrings() -> None:
    runtime = posix_runtime(platform_id="linux")

    assert not runtime.is_parallel_api_command("echo scripts/full_api_parallel_runner.py")
    assert not runtime.is_parallel_api_command("python scripts/full_api_parallel_runner.py && echo bad")
    assert not runtime.is_parallel_api_command("python scripts/full_api_parallel_runner.py ; echo bad")
    assert not runtime.is_parallel_api_command(
        "cmd /c dangerous && python scripts/run_pipeline_step.py --run-root runs/x"
    )
    assert not runtime.is_parallel_api_command("powershell Write-Host scripts/run_full_api_parallel_with_watch.ps1")


def test_runtime_recognizes_guarded_pipeline_commands_across_path_styles() -> None:
    runtime = posix_runtime(platform_id="wsl")

    assert runtime.is_guarded_pipeline_command("python scripts/run_pipeline_step.py --run-root runs/x --stage clean")
    assert runtime.is_guarded_pipeline_command("python scripts\\run_pipeline_step.py --run-root runs\\x --stage clean")
    assert not runtime.is_guarded_pipeline_command("python scripts/clean_documents.py")
    assert not runtime.is_guarded_pipeline_command(
        "cmd /c dangerous && python scripts/run_pipeline_step.py --run-root runs/x"
    )
    assert not runtime.is_guarded_pipeline_command("python scripts/run_pipeline_step.py ; echo bad")
    assert not runtime.is_guarded_pipeline_command("python scripts/run_pipeline_step.py && echo bad")


def test_windows_launch_shell_command_uses_powershell(tmp_path: Path) -> None:
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess(pid=1111)

    runtime = windows_runtime(popen_factory=fake_popen)
    handle = runtime.launch_shell_command(
        "python scripts\\full_api_parallel_runner.py --dry-run",
        cwd=tmp_path,
        log_path=tmp_path / "launch.log",
    )

    assert handle.pid == 1111
    assert handle.process_group_id is None
    assert calls[0][0][0][:4] == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"]


def test_posix_launch_shell_command_starts_new_session(tmp_path: Path) -> None:
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess(pid=2222)

    runtime = posix_runtime(platform_id="wsl", popen_factory=fake_popen)
    handle = runtime.launch_shell_command(
        "python scripts/full_api_parallel_runner.py --dry-run",
        cwd=tmp_path,
        log_path=tmp_path / "launch.log",
    )

    assert handle.pid == 2222
    assert handle.process_group_id == 2222
    assert calls[0][0][0] == ["bash", "-lc", "python scripts/full_api_parallel_runner.py --dry-run"]
    assert calls[0][1]["start_new_session"] is True


def test_windows_launch_worker_runs_argv_directly(tmp_path: Path) -> None:
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess(pid=3333)

    runtime = windows_runtime(popen_factory=fake_popen)
    handle = runtime.launch_worker(
        ["python", "scripts/full_api_parallel_runner.py", "--dry-run"],
        cwd=tmp_path,
        log_path=tmp_path / "worker.log",
    )

    assert handle.pid == 3333
    assert handle.process_group_id is None
    assert calls[0][0][0] == ["python", "scripts/full_api_parallel_runner.py", "--dry-run"]
    assert calls[0][1]["cwd"] == str(tmp_path)
    assert calls[0][1]["stderr"] == subprocess.STDOUT
    assert calls[0][1]["text"] is True
    assert "start_new_session" not in calls[0][1]


def test_posix_launch_worker_starts_new_session(tmp_path: Path) -> None:
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess(pid=4444)

    runtime = posix_runtime(platform_id="wsl", popen_factory=fake_popen)
    handle = runtime.launch_worker(
        ["python3", "scripts/full_api_parallel_runner.py", "--dry-run"],
        cwd=tmp_path,
        log_path=tmp_path / "worker.log",
    )

    assert handle.pid == 4444
    assert handle.process_group_id == 4444
    assert calls[0][0][0] == ["python3", "scripts/full_api_parallel_runner.py", "--dry-run"]
    assert calls[0][1]["cwd"] == str(tmp_path)
    assert calls[0][1]["stderr"] == subprocess.STDOUT
    assert calls[0][1]["text"] is True
    assert calls[0][1]["start_new_session"] is True


def test_windows_stop_process_tree_uses_taskkill() -> None:
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeCompletedProcess()

    runtime = windows_runtime(process_runner=fake_runner)
    result = runtime.stop_process_tree(ProcessHandle(pid=1234, process_group_id=None))

    assert result.status == "stopped"
    assert result.return_code == 0
    assert result.command == "taskkill /PID 1234 /T /F"
    assert calls[0][0][0] == ["taskkill", "/PID", "1234", "/T", "/F"]


def test_posix_stop_process_tree_uses_process_group() -> None:
    signals = []

    def fake_killpg(process_group_id: int, signal_number: int) -> None:
        signals.append((process_group_id, signal_number))

    runtime = posix_runtime(platform_id="wsl", killpg=fake_killpg)
    result = runtime.stop_process_tree(ProcessHandle(pid=1234, process_group_id=4321))

    assert result.status == "stopped"
    assert result.return_code == 0
    assert result.command == "kill -- -4321"
    assert signals[0][0] == 4321


def test_posix_stop_process_tree_escalates_after_wait_timeout() -> None:
    signals = []
    process = FakeTimeoutThenStoppedProcess()
    sigkill = getattr(signal, "SIGKILL", 9)

    def fake_killpg(process_group_id: int, signal_number: int) -> None:
        signals.append((process_group_id, signal_number))

    runtime = posix_runtime(platform_id="wsl", killpg=fake_killpg)
    result = runtime.stop_process_tree(ProcessHandle(pid=1234, process_group_id=4321, process=process))

    assert result.status == "stopped"
    assert result.return_code == 0
    assert result.command == "kill -- -4321"
    assert signals == [(4321, signal.SIGTERM), (4321, sigkill)]
    assert process.wait_calls == [5, 5]


def test_detect_platform_can_be_forced() -> None:
    assert detect_platform("windows").platform_id == "windows"
    assert detect_platform("linux").platform_id == "linux"
    assert detect_platform("wsl").platform_id == "wsl"
