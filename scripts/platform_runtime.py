from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


PopenFactory = Callable[..., Any]
ProcessRunner = Callable[..., Any]
KillProcessGroup = Callable[[int, int], None]
DEFAULT_KILLPG: KillProcessGroup
POSIX_SIGKILL = getattr(signal, "SIGKILL", 9)


def _missing_killpg(process_group_id: int, signal_number: int) -> None:
    raise OSError(f"os.killpg is not available for process group {process_group_id}")


DEFAULT_KILLPG = getattr(os, "killpg", _missing_killpg)


@dataclass(frozen=True)
class ProcessHandle:
    pid: int
    process_group_id: int | None = None
    process: Any | None = None


@dataclass(frozen=True)
class StopResult:
    status: str
    return_code: int
    command: str
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class PlatformRuntime:
    platform_id: str
    path_style: str
    shell: str
    python_executable: str
    popen_factory: PopenFactory = subprocess.Popen
    process_runner: ProcessRunner = subprocess.run
    killpg: KillProcessGroup = DEFAULT_KILLPG

    def format_command(self, argv: Sequence[str | os.PathLike[str]]) -> str:
        args = [str(arg) for arg in argv]
        if self.path_style == "windows":
            return subprocess.list2cmdline(args)
        return " ".join(shlex.quote(arg) for arg in args)

    def path(self, value: str | os.PathLike[str]) -> str:
        normalized = str(value).replace("\\", "/")
        if self.path_style == "windows":
            return normalized.replace("/", "\\")
        return normalized

    def format_path(self, path: str | os.PathLike[str]) -> str:
        return self.path(path)

    def launch_shell_command(
        self,
        command: str,
        *,
        cwd: str | os.PathLike[str] | None = None,
        log_path: str | os.PathLike[str] | None = None,
    ) -> ProcessHandle:
        stdout_target: Any = subprocess.DEVNULL
        stderr_target: Any = subprocess.STDOUT
        log_file = None
        try:
            if log_path is not None:
                log_file = Path(log_path).open("a", encoding="utf-8")
                stdout_target = log_file

            if self.path_style == "windows":
                process = self.popen_factory(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                    cwd=str(cwd) if cwd is not None else None,
                    stdout=stdout_target,
                    stderr=stderr_target,
                )
                return ProcessHandle(pid=process.pid, process_group_id=None, process=process)

            process = self.popen_factory(
                [self.shell, "-lc", command],
                cwd=str(cwd) if cwd is not None else None,
                stdout=stdout_target,
                stderr=stderr_target,
                start_new_session=True,
            )
            return ProcessHandle(pid=process.pid, process_group_id=process.pid, process=process)
        finally:
            if log_file is not None:
                log_file.close()

    def launch_worker(
        self,
        args: Sequence[str | os.PathLike[str]],
        *,
        cwd: str | os.PathLike[str],
        log_path: str | os.PathLike[str],
    ) -> ProcessHandle:
        argv = [str(arg) for arg in args]
        log_file = Path(log_path).open("a", encoding="utf-8")
        try:
            popen_kwargs: dict[str, Any] = {
                "cwd": str(cwd),
                "stdout": log_file,
                "stderr": subprocess.STDOUT,
                "text": True,
            }
            if self.path_style != "windows":
                popen_kwargs["start_new_session"] = True
            process = self.popen_factory(argv, **popen_kwargs)
            if self.path_style == "windows":
                return ProcessHandle(pid=process.pid, process_group_id=None, process=process)
            return ProcessHandle(pid=process.pid, process_group_id=process.pid, process=process)
        finally:
            log_file.close()

    def stop_process_tree(self, handle: ProcessHandle) -> StopResult:
        if self.path_style == "windows":
            argv = ["taskkill", "/PID", str(handle.pid), "/T", "/F"]
            command = " ".join(argv)
            completed = self.process_runner(argv, capture_output=True, text=True)
            status = "stopped" if completed.returncode == 0 else "failed"
            return StopResult(
                status=status,
                return_code=completed.returncode,
                command=command,
                stdout=getattr(completed, "stdout", "") or "",
                stderr=getattr(completed, "stderr", "") or "",
            )

        process_group_id = handle.process_group_id or handle.pid
        command = f"kill -- -{process_group_id}"
        try:
            self.killpg(process_group_id, signal.SIGTERM)
        except ProcessLookupError as exc:
            return StopResult(status="stopped", return_code=0, command=command, stderr=str(exc))
        except OSError as exc:
            return StopResult(status="stop_failed", return_code=1, command=command, stderr=str(exc))

        wait = getattr(handle.process, "wait", None)
        if not callable(wait):
            return StopResult(status="stopped", return_code=0, command=command)

        try:
            wait(timeout=5)
            return StopResult(status="stopped", return_code=0, command=command)
        except subprocess.TimeoutExpired:
            try:
                self.killpg(process_group_id, POSIX_SIGKILL)
            except ProcessLookupError as exc:
                return StopResult(status="stopped", return_code=0, command=command, stderr=str(exc))
            except OSError as exc:
                return StopResult(status="stop_failed", return_code=1, command=command, stderr=str(exc))

            try:
                wait(timeout=5)
                return StopResult(status="stopped", return_code=0, command=command)
            except subprocess.TimeoutExpired as exc:
                return StopResult(status="stop_failed", return_code=1, command=command, stderr=str(exc))
            except OSError as exc:
                return StopResult(status="stop_failed", return_code=1, command=command, stderr=str(exc))
        except OSError as exc:
            return StopResult(status="stop_failed", return_code=1, command=command, stderr=str(exc))
        return StopResult(status="stopped", return_code=0, command=command)

    def is_parallel_api_command(self, command: str) -> bool:
        if _has_shell_control_operator(command):
            return False
        tokens = _normalized_tokens(command)
        if len(tokens) >= 2 and tokens[0] in {"python", "python3"}:
            return tokens[1] == "scripts/full_api_parallel_runner.py"
        if len(tokens) >= 2 and tokens[0] == "bash":
            return tokens[1] == "scripts/run_full_api_parallel_with_watch.sh"
        if tokens and tokens[0] == "powershell":
            for index, token in enumerate(tokens[:-1]):
                if token.lower() == "-file":
                    return tokens[index + 1] == "scripts/run_full_api_parallel_with_watch.ps1"
        return False

    def is_guarded_pipeline_command(self, command: str) -> bool:
        if _has_shell_control_operator(command):
            return False
        tokens = _normalized_tokens(command)
        return len(tokens) >= 2 and tokens[0] in {"python", "python3"} and tokens[1] == "scripts/run_pipeline_step.py"


def windows_runtime(
    *,
    popen_factory: PopenFactory = subprocess.Popen,
    process_runner: ProcessRunner = subprocess.run,
    killpg: KillProcessGroup = DEFAULT_KILLPG,
) -> PlatformRuntime:
    return PlatformRuntime(
        platform_id="windows",
        path_style="windows",
        shell="powershell",
        python_executable=str(Path(sys.executable).resolve()),
        popen_factory=popen_factory,
        process_runner=process_runner,
        killpg=killpg,
    )


def posix_runtime(
    platform_id: str = "linux",
    *,
    popen_factory: PopenFactory = subprocess.Popen,
    process_runner: ProcessRunner = subprocess.run,
    killpg: KillProcessGroup = DEFAULT_KILLPG,
) -> PlatformRuntime:
    return PlatformRuntime(
        platform_id=platform_id,
        path_style="posix",
        shell="bash",
        python_executable="python3",
        popen_factory=popen_factory,
        process_runner=process_runner,
        killpg=killpg,
    )


def detect_platform(
    platform_id: str = "auto",
    *,
    popen_factory: PopenFactory = subprocess.Popen,
    process_runner: ProcessRunner = subprocess.run,
    killpg: KillProcessGroup = DEFAULT_KILLPG,
) -> PlatformRuntime:
    if platform_id == "windows":
        return windows_runtime(popen_factory=popen_factory, process_runner=process_runner, killpg=killpg)
    if platform_id in {"linux", "wsl"}:
        return posix_runtime(
            platform_id=platform_id,
            popen_factory=popen_factory,
            process_runner=process_runner,
            killpg=killpg,
        )
    if platform_id != "auto":
        raise ValueError(f"Unsupported platform_id: {platform_id}")

    if sys.platform.startswith("win"):
        return windows_runtime(popen_factory=popen_factory, process_runner=process_runner, killpg=killpg)
    if _running_inside_wsl():
        return posix_runtime(
            platform_id="wsl",
            popen_factory=popen_factory,
            process_runner=process_runner,
            killpg=killpg,
        )
    return posix_runtime(platform_id="linux", popen_factory=popen_factory, process_runner=process_runner, killpg=killpg)


def _running_inside_wsl() -> bool:
    try:
        version = Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False
    return "microsoft" in version or "wsl" in version


def _normalize_command_paths(command: str) -> str:
    return command.replace("\\", "/")


def _split_command(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def _normalized_tokens(command: str) -> list[str]:
    return [_normalize_command_paths(token) for token in _split_command(_normalize_command_paths(command))]


def _has_shell_control_operator(command: str) -> bool:
    if "\n" in command or "\r" in command:
        return True
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    return any(token in {"&&", "||", ";", "|", ">", "<", "&"} for token in tokens)
