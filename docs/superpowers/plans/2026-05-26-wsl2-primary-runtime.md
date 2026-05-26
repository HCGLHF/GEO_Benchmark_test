# WSL2 Primary Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make WSL2 the primary runtime for long full API benchmark runs while preserving Windows fallback, current run artifacts, operations logging, UI guarded execution, and safe Git publishing.

**Architecture:** Add `scripts/platform_runtime.py` as the platform seam, then move the full API parallel runner logic into `scripts/full_api_parallel_runner.py`. Keep `.ps1` and `.sh` as thin entrypoints, and update UI planning/execution to call the shared platform adapter instead of hardcoding PowerShell, backslash paths, and `taskkill`.

**Tech Stack:** Python 3.11 standard library, pytest, PowerShell wrapper compatibility, Bash wrapper for WSL/Linux, existing `scripts.pipeline_state`, `scripts.ops_logging`, `scripts.full_api_run_status`, `scripts.merge_full_api_runs`, and `scripts.ui_app`.

---

## File Structure

- Create `scripts/platform_runtime.py`: platform adapter Interface and Windows/POSIX adapters for command formatting, launch, and stop.
- Create `tests/test_platform_runtime.py`: unit tests for command formatting, platform detection, launch metadata, and stop behavior.
- Create `scripts/full_api_parallel_runner.py`: Python core runner for dry-run, worker launch, monitoring, exit-code collection, merge, pipeline state, and ops summary.
- Create `tests/test_full_api_parallel_runner.py`: focused tests for dry-run parity and fake-runtime real execution without API calls.
- Modify `scripts/run_full_api_parallel_with_watch.ps1`: keep the current PowerShell parameters, forward them to the Python core runner, and return the Python exit code.
- Create `scripts/run_full_api_parallel_with_watch.sh`: thin WSL/Linux entrypoint that calls the Python core runner.
- Modify `tests/test_full_api_parallel_with_watch.py`: replace brittle PowerShell internals assertions with wrapper and runner contract tests.
- Modify `scripts/ui_app/run_plan.py`: add platform-aware path and command generation.
- Modify `tests/test_ui_run_plan.py`: assert Windows and WSL command previews.
- Modify `scripts/ui_app/execution.py`: use platform adapters for launch, stop, resume, and trusted command checks.
- Modify `tests/test_ui_execution.py`: assert Windows process-tree stop and POSIX process-group stop.
- Modify `scripts/ui_app/server.py`: pass the platform value through run-plan and launch requests when present; default to auto-detection.
- Create `docs/adr/0002-wsl2-primary-runtime.md`: record WSL2 as primary runtime and Windows as fallback.
- Create `docs/wsl2-runbook.md`: user-facing WSL setup, clone, test, run, stop, resume, and publish instructions.
- Modify `docs/architecture.md`, `docs/risks.md`, `docs/next.md`, and `docs/ui-console.md`: record the new runner boundary and WSL operating model.

## Task 1: Platform Runtime Adapter

**Files:**
- Create: `scripts/platform_runtime.py`
- Create: `tests/test_platform_runtime.py`

- [ ] **Step 1: Write platform adapter tests**

Add `tests/test_platform_runtime.py`:

```python
from __future__ import annotations

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


def test_runtime_recognizes_parallel_api_commands() -> None:
    runtime = posix_runtime(platform_id="linux")

    assert runtime.is_parallel_api_command("python scripts/full_api_parallel_runner.py --run-mode test")
    assert runtime.is_parallel_api_command("bash scripts/run_full_api_parallel_with_watch.sh --run-mode test")
    assert runtime.is_parallel_api_command(
        "powershell -ExecutionPolicy Bypass -File scripts\\run_full_api_parallel_with_watch.ps1 -RunMode test"
    )
    assert not runtime.is_parallel_api_command("python scripts/run_pipeline_step.py --run-root runs/x")


def test_runtime_recognizes_guarded_pipeline_commands_across_path_styles() -> None:
    runtime = posix_runtime(platform_id="wsl")

    assert runtime.is_guarded_pipeline_command("python scripts/run_pipeline_step.py --run-root runs/x --stage clean")
    assert runtime.is_guarded_pipeline_command("python scripts\\run_pipeline_step.py --run-root runs\\x --stage clean")
    assert not runtime.is_guarded_pipeline_command("python scripts/clean_documents.py")


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


def test_detect_platform_can_be_forced() -> None:
    assert detect_platform("windows").platform_id == "windows"
    assert detect_platform("linux").platform_id == "linux"
    assert detect_platform("wsl").platform_id == "wsl"
```

- [ ] **Step 2: Run the platform adapter tests and confirm they fail**

Run:

```powershell
pytest tests\test_platform_runtime.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'scripts.platform_runtime'`.

- [ ] **Step 3: Implement `scripts/platform_runtime.py`**

Create `scripts/platform_runtime.py`:

```python
from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


PopenFactory = Callable
RunFactory = Callable
KillPg = Callable[[int, int], None]


@dataclass(frozen=True)
class ProcessHandle:
    pid: int
    process_group_id: int | None = None


@dataclass(frozen=True)
class StopResult:
    status: str
    return_code: int
    command: str
    stdout: str = ""
    stderr: str = ""


class PlatformRuntime:
    def __init__(
        self,
        *,
        platform_id: str,
        path_style: str,
        shell: str,
        python_executable: str,
        popen_factory: PopenFactory = subprocess.Popen,
        process_runner: RunFactory = subprocess.run,
        killpg: KillPg = os.killpg,
    ) -> None:
        self.platform_id = platform_id
        self.path_style = path_style
        self.shell = shell
        self.python_executable = python_executable
        self._popen_factory = popen_factory
        self._process_runner = process_runner
        self._killpg = killpg

    @property
    def is_windows(self) -> bool:
        return self.platform_id == "windows"

    @property
    def is_posix(self) -> bool:
        return not self.is_windows

    def path(self, value: str) -> str:
        return value.replace("/", "\\") if self.path_style == "windows" else value.replace("\\", "/")

    def format_command(self, args: list[str]) -> str:
        if self.is_windows:
            return subprocess.list2cmdline([str(arg) for arg in args])
        return " ".join(shlex.quote(str(arg)) for arg in args)

    def launch_worker(self, args: list[str], *, cwd: Path, log_path: Path) -> ProcessHandle:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("a", encoding="utf-8", errors="replace")
        try:
            process = self._popen_factory(
                [str(arg) for arg in args],
                cwd=str(cwd),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
        finally:
            log_handle.close()
        return ProcessHandle(pid=int(process.pid), process_group_id=None)

    def launch_shell_command(self, command: str, *, cwd: Path, log_path: Path) -> ProcessHandle:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("a", encoding="utf-8", errors="replace")
        try:
            if self.is_windows:
                process = self._popen_factory(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                    cwd=str(cwd),
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                return ProcessHandle(pid=int(process.pid), process_group_id=None)
            process = self._popen_factory(
                ["bash", "-lc", command],
                cwd=str(cwd),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            return ProcessHandle(pid=int(process.pid), process_group_id=int(process.pid))
        finally:
            log_handle.close()

    def stop_process_tree(self, handle: ProcessHandle) -> StopResult:
        if handle.pid <= 0:
            return StopResult(status="stop_failed", return_code=1, command="", stderr="invalid pid")
        if self.is_windows:
            command = ["taskkill", "/PID", str(handle.pid), "/T", "/F"]
            completed = self._process_runner(command, capture_output=True, text=True)
            return_code = int(getattr(completed, "returncode", 1))
            return StopResult(
                status="stopped" if return_code == 0 else "stop_failed",
                return_code=return_code,
                command=f"taskkill /PID {handle.pid} /T /F",
                stdout=str(getattr(completed, "stdout", "") or ""),
                stderr=str(getattr(completed, "stderr", "") or ""),
            )
        process_group_id = handle.process_group_id or handle.pid
        command_text = f"kill -- -{process_group_id}"
        try:
            self._killpg(int(process_group_id), signal.SIGTERM)
        except ProcessLookupError:
            return StopResult(status="stopped", return_code=0, command=command_text)
        except OSError as exc:
            return StopResult(status="stop_failed", return_code=1, command=command_text, stderr=str(exc))
        return StopResult(status="stopped", return_code=0, command=command_text)

    def is_parallel_api_command(self, command: str) -> bool:
        normalized = command.replace("\\", "/").lower()
        return (
            "scripts/full_api_parallel_runner.py" in normalized
            or "scripts/run_full_api_parallel_with_watch.ps1" in normalized
            or "scripts/run_full_api_parallel_with_watch.sh" in normalized
        )

    def is_guarded_pipeline_command(self, command: str) -> bool:
        normalized = command.replace("\\", "/").strip().lower()
        return normalized.startswith("python scripts/run_pipeline_step.py") or normalized.startswith(
            "python3 scripts/run_pipeline_step.py"
        )


def windows_runtime(
    *,
    popen_factory: PopenFactory = subprocess.Popen,
    process_runner: RunFactory = subprocess.run,
) -> PlatformRuntime:
    return PlatformRuntime(
        platform_id="windows",
        path_style="windows",
        shell="powershell",
        python_executable="python",
        popen_factory=popen_factory,
        process_runner=process_runner,
    )


def posix_runtime(
    *,
    platform_id: str = "linux",
    popen_factory: PopenFactory = subprocess.Popen,
    process_runner: RunFactory = subprocess.run,
    killpg: KillPg = os.killpg,
) -> PlatformRuntime:
    return PlatformRuntime(
        platform_id=platform_id,
        path_style="posix",
        shell="bash",
        python_executable="python",
        popen_factory=popen_factory,
        process_runner=process_runner,
        killpg=killpg,
    )


def _running_inside_wsl() -> bool:
    version_path = Path("/proc/version")
    if not version_path.exists():
        return False
    try:
        text = version_path.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return "microsoft" in text or "wsl" in text


def detect_platform(
    platform_id: str = "auto",
    *,
    popen_factory: PopenFactory = subprocess.Popen,
    process_runner: RunFactory = subprocess.run,
    killpg: KillPg = os.killpg,
) -> PlatformRuntime:
    value = (platform_id or "auto").strip().lower()
    if value == "windows":
        return windows_runtime(popen_factory=popen_factory, process_runner=process_runner)
    if value == "wsl":
        return posix_runtime(platform_id="wsl", popen_factory=popen_factory, process_runner=process_runner, killpg=killpg)
    if value == "linux":
        return posix_runtime(platform_id="linux", popen_factory=popen_factory, process_runner=process_runner, killpg=killpg)
    if sys.platform.startswith("win"):
        return windows_runtime(popen_factory=popen_factory, process_runner=process_runner)
    if _running_inside_wsl():
        return posix_runtime(platform_id="wsl", popen_factory=popen_factory, process_runner=process_runner, killpg=killpg)
    return posix_runtime(platform_id="linux", popen_factory=popen_factory, process_runner=process_runner, killpg=killpg)
```

- [ ] **Step 4: Run the platform adapter tests and confirm they pass**

Run:

```powershell
pytest tests\test_platform_runtime.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add scripts/platform_runtime.py tests/test_platform_runtime.py
git commit -m "feat: add platform runtime adapter"
```

Expected: commit succeeds.

## Task 2: Python Core Runner Dry-Run Contract

**Files:**
- Create: `scripts/full_api_parallel_runner.py`
- Create: `tests/test_full_api_parallel_runner.py`

- [ ] **Step 1: Write dry-run tests for the Python runner**

Add `tests/test_full_api_parallel_runner.py`:

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_full_api_parallel_runner_dry_run_prints_expected_contract(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/full_api_parallel_runner.py",
            "--run-mode",
            "test",
            "--run-root",
            str(tmp_path / "full_api_parallel"),
            "--run-stamp",
            "fixed_stamp",
            "--models",
            "openai/gpt-4.1-mini",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "DRY RUN: full API parallel run with monitoring" in result.stdout
    assert f"Run root: {tmp_path / 'full_api_parallel' / 'fixed_stamp'}" in result.stdout
    assert "Run mode: test" in result.stdout
    assert "Queries per model: 2" in result.stdout
    assert "Selected models: openai/gpt-4.1-mini" in result.stdout
    assert "Progress HTML:" in result.stdout
    assert "Pipeline manifest:" in result.stdout
    assert "Pipeline state:" in result.stdout
    assert "Model: openai/gpt-4.1-mini" in result.stdout
    assert "scripts/run_full_api_client_acquisition.py" in result.stdout.replace("\\", "/")
    assert "--cache-path" in result.stdout
    assert "Watch: python scripts/watch_full_api_run.py --run-dir" in result.stdout.replace("\\", "/")
    assert "Merge:" in result.stdout
    assert "scripts/merge_full_api_runs.py" in result.stdout.replace("\\", "/")


def test_full_api_parallel_runner_quick_and_standard_query_defaults(tmp_path: Path) -> None:
    quick = subprocess.run(
        [
            sys.executable,
            "scripts/full_api_parallel_runner.py",
            "--run-mode",
            "quick",
            "--run-root",
            str(tmp_path / "quick"),
            "--run-stamp",
            "stamp",
            "--models",
            "openai/gpt-4.1-mini",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    standard = subprocess.run(
        [
            sys.executable,
            "scripts/full_api_parallel_runner.py",
            "--run-mode",
            "standard",
            "--run-root",
            str(tmp_path / "standard"),
            "--run-stamp",
            "stamp",
            "--models",
            "openai/gpt-4.1-mini",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert quick.returncode == 0, quick.stderr
    assert standard.returncode == 0, standard.stderr
    assert "Queries per model: 50" in quick.stdout
    assert "Queries per model: 200" in standard.stdout


def test_full_api_parallel_runner_rejects_empty_model_list(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/full_api_parallel_runner.py",
            "--run-root",
            str(tmp_path / "full_api_parallel"),
            "--models",
            "",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "No models selected" in result.stderr
```

- [ ] **Step 2: Run the runner dry-run tests and confirm they fail**

Run:

```powershell
pytest tests\test_full_api_parallel_runner.py -q
```

Expected: fail because `scripts/full_api_parallel_runner.py` does not exist.

- [ ] **Step 3: Implement dry-run support in `scripts/full_api_parallel_runner.py`**

Create `scripts/full_api_parallel_runner.py` with dry-run, option parsing, model resolution, worker planning, and command preview:

```python
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ops_logging import write_event, write_summary
from scripts.pipeline_state import append_event, initialize_manifest
from scripts.platform_runtime import PlatformRuntime, detect_platform


DEFAULT_MODELS = [
    "openai/gpt-4.1-mini",
    "google/gemini-3.5-flash",
    "perplexity/sonar-pro",
    "deepseek/deepseek-v4-flash",
    "qwen/qwen3.7-max",
    "x-ai/grok-build-0.1",
]
DOUBAO_MODEL = "bytedance-seed/seed-2.0-pro"


@dataclass(frozen=True)
class RunnerOptions:
    config: str = "config/client_acquisition_simulator.yaml"
    run_mode: str = "quick"
    queries_per_model: int | None = None
    run_root: str = "runs/full_api_parallel"
    run_stamp: str = ""
    monitor_interval_seconds: int = 30
    seed_queries_run_dir: str = ""
    progress_html_path: str = ""
    models: list[str] | None = None
    include_doubao: bool = False
    skip_merge: bool = False
    dry_run: bool = False
    platform: str = "auto"


@dataclass
class WorkerPlan:
    model: str
    safe_name: str
    run_dir: Path
    cache_path: Path
    python_args: list[str]
    command: str
    seeded_query_count: int = 0
    process: Any | None = None
    exit_code: int | None = None


def safe_model_name(model: str) -> str:
    return model.replace("/", "_").replace(":", "_")


def queries_for_mode(run_mode: str, override: int | None) -> int:
    if override is not None:
        return override
    if run_mode == "test":
        return 2
    if run_mode == "standard":
        return 200
    return 50


def parse_models(raw_models: list[str] | None, include_doubao: bool) -> list[str]:
    if raw_models:
        parsed: list[str] = []
        for entry in raw_models:
            parsed.extend(part.strip() for part in str(entry).split(",") if part.strip())
        models = list(dict.fromkeys(parsed))
    else:
        models = list(DEFAULT_MODELS)
    if include_doubao and DOUBAO_MODEL not in models:
        models.append(DOUBAO_MODEL)
    if not models:
        raise ValueError("No models selected. Pass --models with at least one model id or use the defaults.")
    return models


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_seed_queries(seed_run_dir: str, model: str, limit: int) -> list[dict[str, str]]:
    if not seed_run_dir:
        return []
    seed_path = Path(seed_run_dir) / "api_queries.csv"
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed queries file not found: {seed_path}")
    with seed_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected = [row for row in rows if row.get("scenario_model") == model]
    if not selected and rows:
        counts: dict[str, int] = {}
        for row in rows:
            key = row.get("scenario_model", "")
            counts[key] = counts.get(key, 0) + 1
        fallback_model = max(counts, key=counts.get)
        selected = [row for row in rows if row.get("scenario_model") == fallback_model]
    selected = selected[:limit]
    if not selected:
        raise ValueError(f"No seeded queries found for model {model} in {seed_run_dir}")
    return selected


def build_worker_plans(
    *,
    options: RunnerOptions,
    runtime: PlatformRuntime,
    root: Path,
    cache_root: Path,
    models: list[str],
    queries_per_model: int,
) -> list[WorkerPlan]:
    workers: list[WorkerPlan] = []
    for model in models:
        safe_name = safe_model_name(model)
        run_dir = root / safe_name
        cache_path = cache_root / f"{safe_name}.sqlite"
        python_args = [
            runtime.python_executable,
            runtime.path("scripts/run_full_api_client_acquisition.py"),
            "--config",
            runtime.path(options.config),
            "--include-model",
            model,
            "--queries-per-model",
            str(queries_per_model),
            "--output-dir",
            runtime.path(str(run_dir)),
            "--cache-path",
            runtime.path(str(cache_path)),
            "--ops-run-root",
            runtime.path(str(root)),
        ]
        seeded_count = len(get_seed_queries(options.seed_queries_run_dir, model, queries_per_model)) if options.seed_queries_run_dir else 0
        workers.append(
            WorkerPlan(
                model=model,
                safe_name=safe_name,
                run_dir=run_dir,
                cache_path=cache_path,
                python_args=python_args,
                command=runtime.format_command(python_args),
                seeded_query_count=seeded_count,
            )
        )
    return workers


def merge_args(options: RunnerOptions, runtime: PlatformRuntime, workers: list[WorkerPlan], merged_dir: Path) -> list[str]:
    args = [
        runtime.python_executable,
        runtime.path("scripts/merge_full_api_runs.py"),
        "--config",
        runtime.path(options.config),
        "--runs",
    ]
    args.extend(runtime.path(str(worker.run_dir)) for worker in workers)
    args.extend(["--output-dir", runtime.path(str(merged_dir))])
    return args


def print_dry_run(
    *,
    options: RunnerOptions,
    root: Path,
    progress_html_path: Path,
    workers: list[WorkerPlan],
    merge_command: str,
    queries_per_model: int,
    models: list[str],
) -> int:
    print("DRY RUN: full API parallel run with monitoring")
    print(f"Run root: {root}")
    print(f"Run mode: {options.run_mode}")
    print(f"Queries per model: {queries_per_model}")
    print(f"Selected models: {', '.join(models)}")
    print(f"Progress HTML: {progress_html_path}")
    print(f"Pipeline manifest: {root / 'run_manifest.json'}")
    print(f"Pipeline state: {root / 'pipeline_state.jsonl'}")
    if options.seed_queries_run_dir:
        print(f"Seed queries run: {options.seed_queries_run_dir}")
        print("Scenario generation will resume from seeded api_queries.csv")
    print("")
    for worker in workers:
        print(f"Model: {worker.model}")
        print(f"Run dir: {worker.run_dir}")
        print(f"Cache: {worker.cache_path}")
        if options.seed_queries_run_dir:
            print(f"Seeded queries: {worker.seeded_query_count}")
        print(worker.command)
        print(f"Watch: python scripts/watch_full_api_run.py --run-dir {worker.run_dir}")
        print("")
    print("Merge:")
    print(merge_command)
    return 0


def run_parallel(options: RunnerOptions, runtime: PlatformRuntime | None = None) -> int:
    runtime = runtime or detect_platform(options.platform)
    queries_per_model = queries_for_mode(options.run_mode, options.queries_per_model)
    models = parse_models(options.models, options.include_doubao)
    stamp = options.run_stamp or timestamp()
    root = Path(options.run_root) / stamp
    cache_root = root / "cache"
    merged_dir = root / "merged"
    progress_html_path = Path(options.progress_html_path) if options.progress_html_path else root / "progress.html"
    workers = build_worker_plans(
        options=options,
        runtime=runtime,
        root=root,
        cache_root=cache_root,
        models=models,
        queries_per_model=queries_per_model,
    )
    merge_command = runtime.format_command(merge_args(options, runtime, workers, merged_dir))
    if options.dry_run:
        return print_dry_run(
            options=options,
            root=root,
            progress_html_path=progress_html_path,
            workers=workers,
            merge_command=merge_command,
            queries_per_model=queries_per_model,
            models=models,
        )
    raise NotImplementedError("Non-dry-run execution is added in Task 3.")


def parse_args(argv: list[str] | None = None) -> RunnerOptions:
    parser = argparse.ArgumentParser(description="Run full API model workers in parallel with monitoring.")
    parser.add_argument("--config", default="config/client_acquisition_simulator.yaml")
    parser.add_argument("--run-mode", choices=["test", "quick", "standard"], default="quick")
    parser.add_argument("--queries-per-model", type=int, default=None)
    parser.add_argument("--run-root", default="runs/full_api_parallel")
    parser.add_argument("--run-stamp", default="")
    parser.add_argument("--monitor-interval-seconds", type=int, default=30)
    parser.add_argument("--seed-queries-run-dir", default="")
    parser.add_argument("--progress-html-path", default="")
    parser.add_argument("--models", action="append", default=[])
    parser.add_argument("--include-doubao", action="store_true")
    parser.add_argument("--skip-merge", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--platform", default="auto", choices=["auto", "windows", "linux", "wsl"])
    args = parser.parse_args(argv)
    return RunnerOptions(
        config=args.config,
        run_mode=args.run_mode,
        queries_per_model=args.queries_per_model,
        run_root=args.run_root,
        run_stamp=args.run_stamp,
        monitor_interval_seconds=args.monitor_interval_seconds,
        seed_queries_run_dir=args.seed_queries_run_dir,
        progress_html_path=args.progress_html_path,
        models=args.models,
        include_doubao=args.include_doubao,
        skip_merge=args.skip_merge,
        dry_run=args.dry_run,
        platform=args.platform,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        return run_parallel(parse_args(argv))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the runner dry-run tests and platform tests**

Run:

```powershell
pytest tests\test_full_api_parallel_runner.py tests\test_platform_runtime.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add scripts/full_api_parallel_runner.py tests/test_full_api_parallel_runner.py
git commit -m "feat: add python full api runner dry run"
```

Expected: commit succeeds.

## Task 3: Python Core Runner Execution, Merge, and Operations Events

**Files:**
- Modify: `scripts/full_api_parallel_runner.py`
- Modify: `tests/test_full_api_parallel_runner.py`

- [ ] **Step 1: Add fake-runtime execution tests**

Append to `tests/test_full_api_parallel_runner.py`:

```python
import json

from scripts.full_api_parallel_runner import RunnerOptions, run_parallel
from scripts.pipeline_state import read_pipeline_status
from scripts.platform_runtime import ProcessHandle


class FakeWorkerProcess:
    def __init__(self, returncode: int = 0):
        self.pid = 9000
        self.returncode = returncode
        self._poll_count = 0

    def poll(self):
        self._poll_count += 1
        return self.returncode


class FakeRuntime:
    platform_id = "wsl"
    path_style = "posix"
    python_executable = "python"

    def __init__(self):
        self.launched = []

    def path(self, value: str) -> str:
        return value.replace("\\", "/")

    def format_command(self, args: list[str]) -> str:
        return " ".join(str(arg) for arg in args)

    def launch_worker(self, args: list[str], *, cwd: Path, log_path: Path) -> ProcessHandle:
        self.launched.append(args)
        output_dir = Path(args[args.index("--output-dir") + 1])
        model = args[args.index("--include-model") + 1]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "run_config.resolved.json").write_text(
            json.dumps(
                {
                    "models": [{"provider": "openrouter", "model": model}],
                    "client_acquisition": {"queries_per_model": 1},
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "api_queries.csv").write_text("query_id,query\nq001,Need GEO\n", encoding="utf-8")
        (output_dir / "retrieval_by_model.csv").write_text("query_id,model\nq001,model\n", encoding="utf-8")
        (output_dir / "model_answer_evaluations.csv").write_text(
            "query_id,model,error\nq001,model,\n",
            encoding="utf-8",
        )
        (output_dir / "api_orchestrator_attempts.jsonl").write_text(
            json.dumps({"task_type": "rerank", "model": model, "status": "api_call"}) + "\n"
            + json.dumps({"task_type": "answer", "model": model, "status": "api_call"}) + "\n",
            encoding="utf-8",
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("fake worker complete\n", encoding="utf-8")
        return ProcessHandle(pid=9000, process_group_id=None)

    def is_parallel_api_command(self, command: str) -> bool:
        return "full_api_parallel_runner.py" in command

    def is_guarded_pipeline_command(self, command: str) -> bool:
        return command.startswith("python scripts/run_pipeline_step.py")


def test_full_api_parallel_runner_fake_execution_writes_run_contracts(tmp_path: Path, monkeypatch) -> None:
    runtime = FakeRuntime()

    def fake_run(args, check=False, text=True, capture_output=False):
        class Result:
            returncode = 0
            stdout = json.dumps({"status": "complete", "fatal_count": 0, "warning_count": 0, "fatals": [], "warnings": []})
            stderr = ""

        if "merge_full_api_runs.py" in " ".join(str(arg) for arg in args):
            output_dir = Path(args[args.index("--output-dir") + 1])
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "competitive_gap_report.md").write_text("# Report\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr("scripts.full_api_parallel_runner.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.full_api_parallel_runner.time.sleep", lambda seconds: None)

    result = run_parallel(
        RunnerOptions(
            run_mode="test",
            queries_per_model=1,
            run_root=str(tmp_path / "full_api_parallel"),
            run_stamp="fixed_stamp",
            models=["openai/gpt-4.1-mini"],
        ),
        runtime=runtime,
    )

    run_root = tmp_path / "full_api_parallel" / "fixed_stamp"
    assert result == 0
    assert (run_root / "worker_exit_codes.json").exists()
    assert json.loads((run_root / "worker_exit_codes.json").read_text(encoding="utf-8")) == {"openai_gpt-4.1-mini": "0"}
    assert (run_root / "ops_summary.json").exists()
    assert (run_root / "merged" / "competitive_gap_report.md").exists()
    status = read_pipeline_status(run_root)
    assert status["manifest"]["run_type"] == "full_api_parallel"
    assert status["stages"]["answer"]["status"] == "completed"
    assert status["stages"]["merge"]["status"] == "completed"
    assert status["stages"]["report"]["status"] == "completed"
```

- [ ] **Step 2: Run the fake execution test and confirm it fails**

Run:

```powershell
pytest tests\test_full_api_parallel_runner.py::test_full_api_parallel_runner_fake_execution_writes_run_contracts -q
```

Expected: fail with `NotImplementedError: Non-dry-run execution is added in Task 3.`

- [ ] **Step 3: Implement execution, status, merge, and summary behavior**

In `scripts/full_api_parallel_runner.py`, add these functions above `run_parallel`:

```python
def write_seed_queries(seed_run_dir: str, model: str, out_dir: Path, limit: int, runtime: PlatformRuntime) -> int:
    if not seed_run_dir:
        return 0
    rows = get_seed_queries(seed_run_dir, model, limit)
    args = [
        runtime.python_executable,
        runtime.path("scripts/seed_api_queries.py"),
        "--seed-run-dir",
        runtime.path(seed_run_dir),
        "--model",
        model,
        "--output-dir",
        runtime.path(str(out_dir)),
        "--limit",
        str(limit),
    ]
    completed = subprocess.run(args, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout or f"Failed to seed queries for {model}")
    return len(rows)


def render_progress_html(runtime: PlatformRuntime, run_dirs: list[Path], output_path: Path) -> None:
    args = [
        runtime.python_executable,
        runtime.path("scripts/render_full_api_progress_html.py"),
        "--run-dirs",
    ]
    args.extend(runtime.path(str(run_dir)) for run_dir in run_dirs)
    args.extend(["--output", runtime.path(str(output_path)), "--title", "Full API Parallel Progress"])
    completed = subprocess.run(args, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        print(f"Warning: could not render progress HTML at {output_path}", file=sys.stderr)


def classify_run_status(runtime: PlatformRuntime, run_dirs: list[Path], exit_code_json_path: Path) -> dict[str, Any]:
    args = [runtime.python_executable, runtime.path("scripts/full_api_run_status.py")]
    for run_dir in run_dirs:
        args.extend(["--run-dir", runtime.path(str(run_dir))])
    args.extend(["--exit-code-file", runtime.path(str(exit_code_json_path))])
    completed = subprocess.run(args, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout or "Could not classify model worker outputs.")
    return json.loads(completed.stdout)


def run_merge(runtime: PlatformRuntime, options: RunnerOptions, workers: list[WorkerPlan], merged_dir: Path) -> None:
    args = merge_args(options, runtime, workers, merged_dir)
    completed = subprocess.run(args, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout or f"Merge failed with exit code {completed.returncode}")
```

Then replace the `raise NotImplementedError` line in `run_parallel` with:

```python
    root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    initialize_manifest(
        run_root=root,
        run_type="full_api_parallel",
        stages=["crawl", "clean", "chunk", "index", "AWS sync", "scenario_generation", "rerank", "answer", "merge", "report"],
        models=models,
        metadata={"run_mode": options.run_mode, "queries_per_model": queries_per_model},
    )
    write_event(
        root,
        level="info",
        event_type="run_started",
        message="Full API parallel run started.",
        details={"run_mode": options.run_mode, "queries_per_model": queries_per_model},
        source="scripts/full_api_parallel_runner.py",
    )
    append_event(root, stage="scenario_generation", status="running", message="Parallel model workers are starting.")
    print(f"Starting full API single-model runs under {root}")
    for worker in workers:
        worker.run_dir.mkdir(parents=True, exist_ok=True)
        if options.seed_queries_run_dir:
            worker.seeded_query_count = write_seed_queries(
                options.seed_queries_run_dir,
                worker.model,
                worker.run_dir,
                queries_per_model,
                runtime,
            )
            print(f"Seeded {worker.seeded_query_count} existing queries for {worker.model}")
        (worker.run_dir / "worker_python_args.json").write_text(
            json.dumps(worker.python_args, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        append_event(root, stage="rerank", status="running", model=worker.model, message="Worker started.")
        handle = runtime.launch_worker(worker.python_args, cwd=Path.cwd(), log_path=worker.run_dir / "worker.log")
        worker.process = handle
        print(f"Launching {worker.model} -> {worker.run_dir}")

    if options.seed_queries_run_dir:
        append_event(root, stage="scenario_generation", status="completed", message="Seeded queries copied; scenario generation skipped.")

    render_progress_html(runtime, [worker.run_dir for worker in workers], progress_html_path)
    pending = set(worker.safe_name for worker in workers)
    while pending:
        for worker in workers:
            if worker.safe_name not in pending:
                continue
            process = getattr(worker.process, "process", None)
            return_code = process.poll() if process is not None else 0
            if return_code is None:
                continue
            worker.exit_code = int(return_code)
            (worker.run_dir / "worker_exit_code.txt").write_text(str(worker.exit_code), encoding="utf-8")
            pending.remove(worker.safe_name)
            if worker.exit_code == 0:
                append_event(root, stage="answer", status="completed", model=worker.model, message="Worker completed.")
            else:
                append_event(
                    root,
                    stage="answer",
                    status="failed",
                    model=worker.model,
                    message="Worker failed.",
                    details={"exit_code": worker.exit_code},
                )
                write_event(
                    root,
                    level="error",
                    event_type="worker_failed",
                    stage="answer",
                    model=worker.model,
                    message="Worker failed.",
                    details={"exit_code": worker.exit_code},
                    source="scripts/full_api_parallel_runner.py",
                )
        if pending:
            render_progress_html(runtime, [worker.run_dir for worker in workers], progress_html_path)
            time.sleep(options.monitor_interval_seconds)

    render_progress_html(runtime, [worker.run_dir for worker in workers], progress_html_path)
    exit_codes = {worker.safe_name: str(worker.exit_code if worker.exit_code is not None else 1) for worker in workers}
    exit_code_json_path = root / "worker_exit_codes.json"
    exit_code_json_path.write_text(json.dumps(exit_codes, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    run_status = classify_run_status(runtime, [worker.run_dir for worker in workers], exit_code_json_path)

    if int(run_status.get("fatal_count") or 0) > 0:
        append_event(root, stage="answer", status="failed", message="One or more model workers produced incomplete outputs.")
        write_event(
            root,
            level="error",
            event_type="stage_failed",
            stage="answer",
            message="One or more model workers produced incomplete outputs.",
            source="scripts/full_api_parallel_runner.py",
        )
        write_summary(root)
        return 1

    if int(run_status.get("warning_count") or 0) > 0:
        append_event(root, stage="answer", status="complete_with_model_warnings", message="Model workers completed with API warnings.")
        write_event(
            root,
            level="warning",
            event_type="stage_completed",
            stage="answer",
            message="Model workers completed with API warnings.",
            source="scripts/full_api_parallel_runner.py",
        )
    else:
        append_event(root, stage="answer", status="completed", message="All model workers completed.")
        write_event(
            root,
            level="info",
            event_type="stage_completed",
            stage="answer",
            message="All model workers completed.",
            source="scripts/full_api_parallel_runner.py",
        )

    if options.skip_merge:
        append_event(root, stage="merge", status="skipped", message="Skip merge set; merge not executed.")
        write_event(
            root,
            level="info",
            event_type="run_completed",
            stage="merge",
            message="Run completed without merge because skip merge was set.",
            source="scripts/full_api_parallel_runner.py",
        )
        write_summary(root)
        return 0

    append_event(root, stage="merge", status="running", message="Merging model workers.")
    try:
        run_merge(runtime, options, workers, merged_dir)
    except RuntimeError as exc:
        append_event(root, stage="merge", status="failed", message="Merge command failed.", details={"error": str(exc)})
        write_event(
            root,
            level="error",
            event_type="stage_failed",
            stage="merge",
            message="Merge command failed.",
            details={"error": str(exc)},
            source="scripts/full_api_parallel_runner.py",
        )
        write_summary(root)
        print(str(exc), file=sys.stderr)
        return 1
    append_event(root, stage="merge", status="completed", message="Merged model workers.")
    append_event(root, stage="report", status="completed", message="Merged report available.")
    write_event(
        root,
        level="info",
        event_type="run_completed",
        stage="report",
        message="Merged report available.",
        source="scripts/full_api_parallel_runner.py",
    )
    write_summary(root)
    print(f"Merged report: {merged_dir / 'competitive_gap_report.md'}")
    return 0
```

Then update `PlatformRuntime.launch_worker` in `scripts/platform_runtime.py` so it returns the process object for parent polling:

```python
@dataclass(frozen=True)
class ProcessHandle:
    pid: int
    process_group_id: int | None = None
    process: Any | None = None
```

Inside `launch_worker`, return:

```python
return ProcessHandle(pid=int(process.pid), process_group_id=None, process=process)
```

Inside `launch_shell_command`, return `process=process` in both Windows and POSIX branches.

- [ ] **Step 4: Run runner execution tests**

Run:

```powershell
pytest tests\test_full_api_parallel_runner.py tests\test_platform_runtime.py tests\test_ops_logging.py tests\test_ops_logs_cli.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add scripts/full_api_parallel_runner.py scripts/platform_runtime.py tests/test_full_api_parallel_runner.py tests/test_platform_runtime.py
git commit -m "feat: execute full api runner from python"
```

Expected: commit succeeds.

## Task 4: Thin PowerShell and Bash Entrypoints

**Files:**
- Modify: `scripts/run_full_api_parallel_with_watch.ps1`
- Create: `scripts/run_full_api_parallel_with_watch.sh`
- Modify: `tests/test_full_api_parallel_with_watch.py`

- [ ] **Step 1: Replace runner internals tests with wrapper contract tests**

In `tests/test_full_api_parallel_with_watch.py`, remove tests that assert internal PowerShell functions such as `Write-OpsEvent`, `ConvertTo-NativeJsonArg`, `Test-WorkerExitCodeReady`, and `Start-Process`. Keep tests for PowerShell dry-run behavior. Add:

```python
def test_powershell_wrapper_delegates_to_python_core_runner() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.ps1").read_text(encoding="utf-8")

    assert "scripts\\full_api_parallel_runner.py" in script_text
    assert "run_full_api_client_acquisition.py" not in script_text
    assert "Start-Process" not in script_text
    assert "taskkill" not in script_text


def test_bash_wrapper_delegates_to_python_core_runner() -> None:
    script_text = Path("scripts/run_full_api_parallel_with_watch.sh").read_text(encoding="utf-8")

    assert "scripts/full_api_parallel_runner.py" in script_text
    assert '"$@"' in script_text
```

Add a Bash dry-run test guarded by Bash availability:

```python
def test_bash_wrapper_dry_run_prints_contract(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available on this Windows host")

    result = subprocess.run(
        [
            bash,
            "scripts/run_full_api_parallel_with_watch.sh",
            "--run-mode",
            "test",
            "--run-root",
            str(tmp_path / "full_api_parallel"),
            "--run-stamp",
            "fixed_stamp",
            "--models",
            "openai/gpt-4.1-mini",
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "DRY RUN: full API parallel run with monitoring" in result.stdout
    assert "Run mode: test" in result.stdout
```

Add imports at the top of the file:

```python
import shutil
import pytest
```

- [ ] **Step 2: Run the wrapper tests and confirm they fail**

Run:

```powershell
pytest tests\test_full_api_parallel_with_watch.py -q
```

Expected: fail because the PowerShell script still contains old internals and the Bash wrapper does not exist.

- [ ] **Step 3: Replace the PowerShell script with a thin wrapper**

Replace `scripts/run_full_api_parallel_with_watch.ps1` with:

```powershell
param(
  [string]$Config = "config\client_acquisition_simulator.yaml",
  [ValidateSet("test", "quick", "standard")]
  [string]$RunMode = "quick",
  [Nullable[int]]$QueriesPerModel = $null,
  [string]$RunRoot = "runs\full_api_parallel",
  [string]$RunStamp = "",
  [int]$MonitorIntervalSeconds = 30,
  [string]$SeedQueriesRunDir = "",
  [string]$ProgressHtmlPath = "",
  [Alias("Models")]
  [string[]]$SelectedModels = @(),
  [switch]$IncludeDoubao,
  [switch]$SkipMerge,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$argsList = @(
  "scripts\full_api_parallel_runner.py",
  "--config", $Config,
  "--run-mode", $RunMode,
  "--run-root", $RunRoot,
  "--monitor-interval-seconds", "$MonitorIntervalSeconds",
  "--platform", "windows"
)

if ($null -ne $QueriesPerModel) {
  $argsList += @("--queries-per-model", "$QueriesPerModel")
}
if ($RunStamp) {
  $argsList += @("--run-stamp", $RunStamp)
}
if ($SeedQueriesRunDir) {
  $argsList += @("--seed-queries-run-dir", $SeedQueriesRunDir)
}
if ($ProgressHtmlPath) {
  $argsList += @("--progress-html-path", $ProgressHtmlPath)
}
if ($SelectedModels.Count -gt 0) {
  $argsList += @("--models", ($SelectedModels -join ","))
}
if ($IncludeDoubao) {
  $argsList += "--include-doubao"
}
if ($SkipMerge) {
  $argsList += "--skip-merge"
}
if ($DryRun) {
  $argsList += "--dry-run"
}

& python @argsList
exit $LASTEXITCODE
```

- [ ] **Step 4: Add the Bash wrapper**

Create `scripts/run_full_api_parallel_with_watch.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

python scripts/full_api_parallel_runner.py --platform "${GEO_RUNTIME_PLATFORM:-auto}" "$@"
```

- [ ] **Step 5: Run wrapper tests**

Run:

```powershell
pytest tests\test_full_api_parallel_with_watch.py tests\test_full_api_parallel_runner.py -q
```

Expected: pass or skip only the Bash wrapper dry-run when Bash is unavailable.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add scripts/run_full_api_parallel_with_watch.ps1 scripts/run_full_api_parallel_with_watch.sh tests/test_full_api_parallel_with_watch.py
git commit -m "feat: add thin full api runner entrypoints"
```

Expected: commit succeeds.

## Task 5: Platform-Aware UI Run Plan

**Files:**
- Modify: `scripts/ui_app/run_plan.py`
- Modify: `scripts/ui_app/server.py`
- Modify: `tests/test_ui_run_plan.py`

- [ ] **Step 1: Add UI plan tests for Windows and WSL commands**

Append to `tests/test_ui_run_plan.py`:

```python
def test_build_run_plan_uses_wsl_posix_commands_when_requested() -> None:
    request = RunPlanRequest(
        platform="wsl",
        run_mode="test",
        selected_models=["openai/gpt-4.1-mini"],
        recrawl_own_site=True,
        rescan_corpus=False,
        parallel_api=True,
        seed_queries_run_dir="runs/client_acquisition_simulator_full_api_20260517_200716",
    )

    plan = build_run_plan(request)

    assert any("python scripts/full_api_parallel_runner.py" in command.command for command in plan.commands)
    assert any("--platform wsl" in command.command for command in plan.commands)
    assert any("scripts/run_pipeline_step.py" in command.command for command in plan.commands)
    assert not any("powershell" in command.command.lower() for command in plan.commands)
    assert not any("scripts\\run_pipeline_step.py" in command.command for command in plan.commands)


def test_build_run_plan_keeps_windows_commands_by_default() -> None:
    request = RunPlanRequest(
        run_mode="test",
        selected_models=["openai/gpt-4.1-mini"],
        recrawl_own_site=False,
        rescan_corpus=False,
        parallel_api=True,
        seed_queries_run_dir="runs/client_acquisition_simulator_full_api_20260517_200716",
    )

    plan = build_run_plan(request)

    assert any("powershell -ExecutionPolicy Bypass -File scripts\\run_full_api_parallel_with_watch.ps1" in command.command for command in plan.commands)
    assert any("-RunMode test" in command.command for command in plan.commands)
```

- [ ] **Step 2: Run UI plan tests and confirm the WSL test fails**

Run:

```powershell
pytest tests\test_ui_run_plan.py -q
```

Expected: fail because `RunPlanRequest` does not have a `platform` field and command generation is Windows-only.

- [ ] **Step 3: Implement platform-aware run planning**

In `scripts/ui_app/run_plan.py`, add the import:

```python
from scripts.platform_runtime import detect_platform
```

Add this field to `RunPlanRequest`:

```python
    platform: str = "auto"
```

Replace `_pipeline_step` with:

```python
def _runtime(request: RunPlanRequest):
    return detect_platform(request.platform)


def _path(request: RunPlanRequest, value: str) -> str:
    return _runtime(request).path(value)


def _python_command(request: RunPlanRequest, script_path: str, *args: str) -> str:
    runtime = _runtime(request)
    return runtime.format_command(["python", runtime.path(script_path), *[runtime.path(arg) if "\\" in arg else arg for arg in args]])


def _pipeline_step(request: RunPlanRequest, stage: str, command: str) -> str:
    runtime = _runtime(request)
    args = [
        "python",
        runtime.path("scripts/run_pipeline_step.py"),
        "--run-root",
        runtime.path(request.pipeline_run_root),
        "--stage",
        stage,
        "--",
    ]
    return runtime.format_command(args) + " " + command
```

Update hardcoded paths inside `build_run_plan` so Windows and WSL receive the same logical files with the runtime path style:

```python
discovered_output = _path(request, "data\\raw\\alpha_update_discovered_urls.csv")
pages_output = _path(request, "data\\raw\\alpha_update_pages.jsonl")
attempts_output = _path(request, "data\\raw\\alpha_update_fetch_attempts.jsonl")
logs_output = _path(request, "data\\raw\\alpha_update_crawl_logs.csv")
processed_dir = _path(request, "data\\processed")
```

Update the reuse command:

```python
reuse_command = "REM Reuse data\\processed and existing BM25 artifacts" if _runtime(request).is_windows else "# Reuse data/processed and existing BM25 artifacts"
```

Update the parallel API command branch:

```python
runtime = _runtime(request)
if runtime.is_windows:
    command = (
        "powershell -ExecutionPolicy Bypass -File scripts\\run_full_api_parallel_with_watch.ps1 "
        f"-RunMode {request.run_mode} "
        f"-QueriesPerModel {queries_per_model} "
        f"-RunRoot {request.api_run_root}"
    )
    if request.run_stamp:
        command += f" -RunStamp {_quote(request.run_stamp)}"
    if request.seed_queries_run_dir and not request.regenerate_scenarios:
        command += f" -SeedQueriesRunDir {_quote(request.seed_queries_run_dir)}"
    if any(model == "bytedance-seed/seed-2.0-pro" for model in request.selected_models):
        command += " -IncludeDoubao"
    if request.selected_models:
        command += " -Models " + _quote(",".join(request.selected_models))
else:
    args = [
        "python",
        "scripts/full_api_parallel_runner.py",
        "--platform",
        runtime.platform_id,
        "--run-mode",
        request.run_mode,
        "--queries-per-model",
        str(queries_per_model),
        "--run-root",
        runtime.path(request.api_run_root),
    ]
    if request.run_stamp:
        args.extend(["--run-stamp", request.run_stamp])
    if request.seed_queries_run_dir and not request.regenerate_scenarios:
        args.extend(["--seed-queries-run-dir", runtime.path(request.seed_queries_run_dir)])
    if any(model == "bytedance-seed/seed-2.0-pro" for model in request.selected_models):
        args.append("--include-doubao")
    if request.selected_models:
        args.extend(["--models", ",".join(request.selected_models)])
    command = runtime.format_command(args)
```

Update the note text for the API plan:

```python
note="Runs one worker per model and renders progress.html while the benchmark is active.",
```

- [ ] **Step 4: Pass platform from server query and POST parameters**

In `scripts/ui_app/server.py`, add this field to both `RunPlanRequest` constructor calls:

```python
                platform=params.get("platform", ["auto"])[0],
```

Use the same line in `_run_request_from_params`.

- [ ] **Step 5: Run UI run plan tests**

Run:

```powershell
pytest tests\test_ui_run_plan.py tests\test_platform_runtime.py -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 5**

Run:

```powershell
git add scripts/ui_app/run_plan.py scripts/ui_app/server.py tests/test_ui_run_plan.py
git commit -m "feat: make ui run plans platform aware"
```

Expected: commit succeeds.

## Task 6: Platform-Aware UI Launch, Stop, and Resume

**Files:**
- Modify: `scripts/ui_app/execution.py`
- Modify: `tests/test_ui_execution.py`

- [ ] **Step 1: Add UI execution tests for POSIX launch and stop**

Append to `tests/test_ui_execution.py`:

```python
def test_launch_guarded_run_records_platform_and_process_group_for_wsl(tmp_path: Path) -> None:
    calls = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    result = launch_guarded_run(
        project_root=tmp_path,
        request=RunPlanRequest(platform="wsl", selected_models=["openai/gpt-4.1-mini"]),
        confirmed=True,
        popen_factory=fake_popen,
        stamp_factory=lambda: "20260526_230000",
    )

    assert result["status"] == "launched"
    assert result["platform"] == "wsl"
    assert result["process_group_id"] == 4242
    assert calls[0][0][0][:2] == ["bash", "-lc"]


def test_stop_guarded_run_uses_posix_process_group_from_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "runs" / "ui_launches" / "20260526_230000" / "launch_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "status": "launched",
                "platform": "wsl",
                "pid": 1234,
                "process_group_id": 4321,
                "command": "python scripts/full_api_parallel_runner.py --run-mode test",
                "monitor_run_root": "runs/full_api_parallel_ui/20260526_230000",
            }
        ),
        encoding="utf-8",
    )
    signals = []

    def fake_killpg(process_group_id: int, signal_number: int) -> None:
        signals.append((process_group_id, signal_number))

    result = stop_guarded_run(
        project_root=tmp_path,
        run_root="runs/full_api_parallel_ui/20260526_230000",
        confirmed=True,
        reason="stalled",
        killpg=fake_killpg,
    )

    assert result["status"] == "stopped"
    assert result["stop_command"] == "kill -- -4321"
    assert signals[0][0] == 4321
```

- [ ] **Step 2: Run UI execution tests and confirm the new tests fail**

Run:

```powershell
pytest tests\test_ui_execution.py -q
```

Expected: fail because `execution.py` still launches PowerShell directly and does not accept `killpg`.

- [ ] **Step 3: Update execution launch to use platform runtime**

In `scripts/ui_app/execution.py`, add imports:

```python
import os

from scripts.platform_runtime import ProcessHandle, detect_platform
```

Change `_api_benchmark_command`:

```python
def _api_benchmark_command(command: str, platform: str = "auto") -> bool:
    return detect_platform(platform).is_parallel_api_command(command)
```

Change `_launch_process` signature:

```python
def _launch_process(
    *,
    root: Path,
    command: str,
    launch_dir: Path,
    log_path: Path,
    manifest_path: Path,
    base_payload: dict[str, Any],
    platform: str,
    popen_factory: PopenFactory,
) -> dict[str, Any]:
```

Replace its process launch body with:

```python
    runtime = detect_platform(platform, popen_factory=popen_factory)
    launch_dir.mkdir(parents=True, exist_ok=True)
    handle = runtime.launch_shell_command(command, cwd=root, log_path=log_path)
    payload = {
        **base_payload,
        "status": "launched",
        "platform": runtime.platform_id,
        "pid": int(handle.pid),
    }
    if handle.process_group_id is not None:
        payload["process_group_id"] = int(handle.process_group_id)
    _write_manifest(manifest_path, payload)
    payload["manifest_path"] = str(manifest_path)
    return payload
```

- [ ] **Step 4: Update stop/resume to use manifest platform**

Update `stop_guarded_run` signature:

```python
def stop_guarded_run(
    *,
    project_root: Path | str,
    run_root: str,
    confirmed: bool,
    reason: str = "",
    process_runner: RunFactory = subprocess.run,
    killpg: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
```

Inside `stop_guarded_run`, derive the runtime from the manifest:

```python
    platform = str(manifest.get("platform") or "windows")
    runtime = detect_platform(platform, process_runner=process_runner, killpg=killpg or os.killpg)
```

Replace the hardcoded taskkill logic with:

```python
    process_group_id = manifest.get("process_group_id")
    handle = ProcessHandle(
        pid=pid,
        process_group_id=int(process_group_id) if process_group_id not in {"", None} else None,
    )
    preview = runtime.stop_process_tree(handle)
    base_payload = {
        "status": "confirmation_required",
        "action": "stop",
        "pid": pid,
        "platform": runtime.platform_id,
        "stop_command": preview.command,
        "monitor_run_root": _normalize_slashes(run_root),
        "manifest_path": str(manifest_path),
        "reason": reason,
    }
    if not confirmed:
        return base_payload
    result = runtime.stop_process_tree(handle)
    return_code = result.return_code
    status = result.status
```

Update manifest stop fields to use `result.stdout`, `result.stderr`, and `result.command`.

Update `resume_guarded_run` and `launch_guarded_run` calls to `_launch_process` so they pass `platform=materialized.platform` for new launches and `platform=str(manifest.get("platform") or "auto")` for resumes.

Update guarded stage rejection:

```python
    if not detect_platform(materialized.platform).is_guarded_pipeline_command(command):
```

- [ ] **Step 5: Run UI execution tests**

Run:

```powershell
pytest tests\test_ui_execution.py tests\test_ui_run_plan.py tests\test_platform_runtime.py -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 6**

Run:

```powershell
git add scripts/ui_app/execution.py tests/test_ui_execution.py
git commit -m "feat: make ui execution platform aware"
```

Expected: commit succeeds.

## Task 7: Documentation, ADR, and WSL Runbook

**Files:**
- Create: `docs/adr/0002-wsl2-primary-runtime.md`
- Create: `docs/wsl2-runbook.md`
- Modify: `docs/architecture.md`
- Modify: `docs/risks.md`
- Modify: `docs/next.md`
- Modify: `docs/ui-console.md`

- [ ] **Step 1: Add ADR 0002**

Create `docs/adr/0002-wsl2-primary-runtime.md`:

```markdown
# ADR 0002: WSL2 Primary Runtime

## Status

Accepted

## Context

Long full API benchmark runs on Windows have recurring operational friction around file locks, process-tree termination, PowerShell encoding, JSON argument escaping, and Git ownership. The local operations logger now gives stable run facts, so the next improvement is to move the long-running execution environment to WSL2 without changing benchmark metrics or run artifacts.

## Decision

WSL2 is the primary runtime for long full API benchmark execution, report merge, and branch publishing. Windows remains a supported fallback and local UI host.

The platform seam lives in `scripts/platform_runtime.py`. The core full API orchestration lives in `scripts/full_api_parallel_runner.py`. PowerShell and Bash entrypoints are thin wrappers over the Python runner.

WSL jobs must run from Linux filesystem storage such as `~/projects/Resourcepool_Gen`, not from Windows-mounted paths such as `/mnt/d/GEO-ALPHA/Resourcepool_Gen`.

## Consequences

- Long-running worker, merge, and stop/resume behavior uses Linux process groups in WSL.
- Windows fallback keeps PowerShell wrapper compatibility.
- The run fact contracts remain unchanged: `run_manifest.json`, `pipeline_state.jsonl`, `ops_events.jsonl`, `ops_summary.json`, `worker_exit_codes.json`, `progress.html`, and merged report artifacts.
- Publishing should happen from a WSL clone or a clean publish repository to avoid Windows Git safe-directory and ownership issues.
```

- [ ] **Step 2: Add WSL runbook**

Create `docs/wsl2-runbook.md`:

```markdown
# WSL2 Runbook

## Rule

Run long benchmark jobs from Linux storage:

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/HCGLHF/GEO_Benchmark_test.git Resourcepool_Gen
cd ~/projects/Resourcepool_Gen
```

Do not run overnight jobs from `/mnt/d/GEO-ALPHA/Resourcepool_Gen`.

## Setup Check

```bash
python3 --version
git --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pytest tests/test_ops_logging.py tests/test_ops_logs_cli.py tests/test_run_pipeline_step.py -q
```

## Dry Run

```bash
source .venv/bin/activate
bash scripts/run_full_api_parallel_with_watch.sh --run-mode test --models openai/gpt-4.1-mini --dry-run
```

## Minimal API Chain Check

Run this only when `.env` contains the intended API keys and credits are available.

```bash
source .venv/bin/activate
bash scripts/run_full_api_parallel_with_watch.sh --run-mode test --models openai/gpt-4.1-mini
python scripts/ops_logs.py doctor --run-root runs/full_api_parallel/20260526_230000
```

Use the actual run stamp printed by the runner when checking `ops_logs.py doctor`.

## Stop And Resume

When launched from the UI inside WSL, stop uses the launch manifest process group. Manual shell runs can be stopped with Ctrl+C from the same terminal. After a forced stop, run:

```bash
python scripts/ops_logs.py doctor --run-root runs/full_api_parallel/20260526_230000
```

Resume uses existing output rows and run-state files as checkpoints.

## Publish Branch

```bash
cd ~/projects/GEO_Benchmark_test
git checkout -b codex/wsl2-primary-runtime
python -m pytest tests/test_ops_logging.py tests/test_ops_logs_cli.py tests/test_run_pipeline_step.py -q
python -m pytest tests/test_ui_run_plan.py tests/test_ui_execution.py tests/test_ui_run_monitor.py -q
python -m pytest tests/test_full_api_run_status.py tests/test_full_api_parallel_runner.py tests/test_full_api_parallel_with_watch.py -q
git status --short
git add .env.example .gitignore CONTEXT.md README.md docs scripts sql tests pyproject.toml geo-resource-library-plan.md
git commit -m "feat: add wsl2 primary runtime"
git push -u origin codex/wsl2-primary-runtime
```
```

- [ ] **Step 3: Update architecture docs**

In `docs/architecture.md`, update the module list entries:

```markdown
- `scripts/platform_runtime.py`: shared platform runtime seam for command formatting, process launch, and stop behavior across Windows, Linux, and WSL.
- `scripts/full_api_parallel_runner.py`: platform-independent full API parallel runner that owns model worker orchestration, status classification, merge, pipeline-state events, and operations summaries.
- `scripts/run_full_api_parallel_with_watch.ps1`: Windows wrapper that forwards existing PowerShell parameters to the Python full API parallel runner.
- `scripts/run_full_api_parallel_with_watch.sh`: WSL/Linux wrapper that forwards shell arguments to the Python full API parallel runner.
```

Update dependency direction:

```markdown
- Platform-specific launch and stop behavior belongs in `scripts/platform_runtime.py`; UI and runner modules should not hardcode PowerShell, Bash, `taskkill`, or process-group details.
- WSL2 is the primary runtime for long full API benchmark runs, report merge, and Git publishing; Windows remains a fallback and UI host.
```

- [ ] **Step 4: Update risks and next-step memory**

In `docs/risks.md`, add:

```markdown
- WSL2 reduces Windows file-lock and process-tree issues only when jobs run from Linux filesystem storage such as `~/projects/Resourcepool_Gen`; running from `/mnt/d/GEO-ALPHA/Resourcepool_Gen` can reintroduce Windows metadata and locking friction.
- Stop/resume now depends on launch manifest platform metadata. If a launch manifest is edited manually, process-group stop can target the wrong process group.
```

At the top of `docs/next.md` under `Done`, add:

```markdown
- Added the WSL2 primary runtime design and implementation plan, choosing a Python core full API runner plus Windows and POSIX platform adapters.
```

Under `Risks`, add:

```markdown
- Codex currently cannot see the user's Ubuntu WSL2 distro from the sandbox Windows user, so final WSL validation must be run by the user inside Ubuntu unless Codex is later attached to that WSL context.
```

Under `Next`, add:

```markdown
1. Execute the WSL2 primary runtime implementation plan and push branch `codex/wsl2-primary-runtime`.
```

- [ ] **Step 5: Update UI console docs**

In `docs/ui-console.md`, add a WSL note near launch/stop documentation:

```markdown
When the UI runs inside WSL, generated API commands use the Python full API runner and POSIX paths. Stop/resume uses process-group metadata from the launch manifest. For long API runs, launch the UI from the WSL clone under `~/projects/Resourcepool_Gen`, not from `/mnt/d/GEO-ALPHA/Resourcepool_Gen`.
```

- [ ] **Step 6: Run documentation grep checks**

Run:

```powershell
rg -n "WSL2|full_api_parallel_runner|platform_runtime|run_full_api_parallel_with_watch.sh" docs scripts tests
```

Expected: relevant references appear in docs, wrappers, runner, and tests.

- [ ] **Step 7: Commit Task 7**

Run:

```powershell
git add docs/adr/0002-wsl2-primary-runtime.md docs/wsl2-runbook.md docs/architecture.md docs/risks.md docs/next.md docs/ui-console.md
git commit -m "docs: document wsl2 primary runtime"
```

Expected: commit succeeds.

## Task 8: Verification and Publish Branch

**Files:**
- No source edits unless tests reveal failures.
- Publish target: WSL clone or `_publish/GEO_Benchmark_test` after ownership is safe.

- [ ] **Step 1: Run focused Windows-side verification**

Run:

```powershell
pytest tests\test_platform_runtime.py tests\test_full_api_parallel_runner.py tests\test_full_api_parallel_with_watch.py tests\test_ui_run_plan.py tests\test_ui_execution.py tests\test_ui_run_monitor.py tests\test_ops_logging.py tests\test_ops_logs_cli.py tests\test_run_pipeline_step.py tests\test_full_api_run_status.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run broader project verification**

Run:

```powershell
pytest -q
```

Expected: all tests pass. If external or environment-specific tests fail because required local services are unavailable, record the exact failing tests and run the focused suite from Step 1 again after any code fix.

- [ ] **Step 3: Run PowerShell wrapper dry-run**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_full_api_parallel_with_watch.ps1 -RunMode test -RunRoot runs\full_api_parallel_verify -RunStamp verify_win -Models openai/gpt-4.1-mini -DryRun
```

Expected: output includes `DRY RUN`, `Run mode: test`, `Queries per model: 2`, and `scripts\full_api_parallel_runner.py`.

- [ ] **Step 4: Prepare WSL clone manually**

Run these commands inside Ubuntu WSL as the user's normal WSL user:

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/HCGLHF/GEO_Benchmark_test.git Resourcepool_Gen
cd ~/projects/Resourcepool_Gen
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Expected: clone and dependency installation succeed inside Linux storage.

- [ ] **Step 5: Sync implementation into WSL clone**

From the Windows working tree, copy only safe source files to the WSL clone. If using WSL shell with Windows path access, run:

```bash
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.venv/' \
  --exclude '.deps/' \
  --exclude '.codex_runtime/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude 'data/' \
  --exclude 'runs/' \
  --exclude 'reports/' \
  --exclude 'output/' \
  --exclude 'vector_db/' \
  /mnt/d/GEO-ALPHA/Resourcepool_Gen/ \
  ~/projects/Resourcepool_Gen/
```

Expected: source, docs, tests, and configs sync; local data and secrets do not sync.

- [ ] **Step 6: Run WSL verification**

Run inside Ubuntu WSL:

```bash
cd ~/projects/Resourcepool_Gen
source .venv/bin/activate
python -m pytest tests/test_platform_runtime.py tests/test_full_api_parallel_runner.py tests/test_full_api_parallel_with_watch.py -q
python -m pytest tests/test_ui_run_plan.py tests/test_ui_execution.py tests/test_ui_run_monitor.py -q
bash scripts/run_full_api_parallel_with_watch.sh --run-mode test --models openai/gpt-4.1-mini --run-root runs/full_api_parallel_verify --run-stamp verify_wsl --dry-run
```

Expected: tests pass and Bash dry-run prints POSIX paths without requiring PowerShell.

- [ ] **Step 7: Create and push the WSL2 branch**

Run inside Ubuntu WSL:

```bash
cd ~/projects/Resourcepool_Gen
git checkout -b codex/wsl2-primary-runtime
git status --short
git add .env.example .gitignore CONTEXT.md README.md docs scripts sql tests pyproject.toml geo-resource-library-plan.md
git status --short
git commit -m "feat: add wsl2 primary runtime"
git push -u origin codex/wsl2-primary-runtime
```

Expected: branch `codex/wsl2-primary-runtime` is pushed to `https://github.com/HCGLHF/GEO_Benchmark_test.git` without data, runs, reports, vector DB files, `.env`, or `.codex_runtime`.

- [ ] **Step 8: Record completion in `docs/next.md` if implementation changed after Task 7**

If Task 8 required code or documentation fixes, add the final verification and branch URL to `docs/next.md` under `Done`:

```markdown
- Verified the WSL2 primary runtime migration with Windows focused tests, WSL focused tests, Bash dry-run, and pushed branch `codex/wsl2-primary-runtime`.
```

Commit any final doc-only update:

```powershell
git add docs/next.md
git commit -m "docs: record wsl2 runtime verification"
```

Expected: commit succeeds if `docs/next.md` changed; skip this commit when there is no final doc change.

## Self-Review Checklist

- Spec coverage: Tasks 1 through 8 cover platform adapter, Python core runner, thin wrappers, UI planning, UI execution, docs/ADR/runbook, WSL verification, and publish branch.
- Logger contract: Tasks 3 and 7 preserve `pipeline_state.jsonl`, `run_manifest.json`, `ops_events.jsonl`, `ops_summary.json`, `worker_exit_codes.json`, `progress.html`, and merged reports.
- Windows fallback: Tasks 4 through 6 keep PowerShell wrapper behavior and Windows `taskkill` stop behavior under tests.
- WSL primary runtime: Tasks 1, 4, 5, 6, 7, and 8 add POSIX paths, Bash wrapper, process-group stop, Linux-storage runbook, and WSL verification.
- Secret/data safety: Task 8 excludes `.env`, `data/`, `runs/`, `reports/`, `output/`, `vector_db/`, `.codex_runtime/`, caches, and dependency directories from publishing.
