# WSL2 Primary Runtime Design

## Goal

Move long-running GEO benchmark execution to WSL2 while keeping Windows usable as a fallback and preserving the current run-output, pipeline-state, and operations-logging contracts.

The migration should reduce Windows-specific file-lock, process-tree, encoding, and Git ownership problems during overnight full API runs, worker completion, report merge, and branch publish.

## Current State

The project now has a useful local operations layer:

- `pipeline_state.jsonl` remains the append-only stage fact log.
- `run_manifest.json` remains the run-level fact contract.
- `ops_events.jsonl` records structured troubleshooting events.
- `ops_summary.json` summarizes run health for humans and the Run Monitor.
- `scripts/ui_app/run_monitor.py` prefers `ops_summary.json` but still checks live facts when the summary is stale.

The main Windows-specific runtime logic is concentrated in:

- `scripts/run_full_api_parallel_with_watch.ps1`
- `scripts/ui_app/run_plan.py`
- `scripts/ui_app/execution.py`
- `scripts/ui_app/server.py`
- tests that assert PowerShell, backslash paths, and `taskkill` behavior

The root workspace is a local Git repository without a remote. The publishable GitHub repository remains `_publish/GEO_Benchmark_test`, whose remote is `https://github.com/HCGLHF/GEO_Benchmark_test.git`.

The user's Windows account has Ubuntu WSL2 installed. The current Codex process runs as a different Windows user and cannot see that Ubuntu instance, so Codex can implement and run Windows-side tests here but cannot perform the final Ubuntu validation unless it is connected to the same WSL environment later.

## Decision

Use a Python core runner with small platform adapters.

WSL2 becomes the primary runtime for full API benchmark execution, report merge, and Git publishing. Windows remains a fallback and UI host.

The core behavior should live in a Python module so the important logic has one implementation:

- model selection
- run stamp and run-root creation
- seed-query copying
- per-model worker launch
- worker exit-code collection
- progress HTML rendering
- worker status classification
- merge execution
- pipeline-state writes
- operations event and summary writes

Windows and WSL/Linux should differ only at the platform adapter layer:

- command preview syntax
- path rendering
- process launch
- process-tree or process-group stop
- launch manifest process metadata

This keeps the run facts stable and gives platform-specific process control locality.

## Non-Goals

- Do not remove Windows support in this migration.
- Do not rewrite the simulator, retrieval, rerank, answer, or report modules.
- Do not change benchmark metrics or merge semantics.
- Do not create a second pipeline-state or operations-log format.
- Do not run long benchmark jobs from Windows-mounted paths such as `/mnt/d/GEO-ALPHA/Resourcepool_Gen` inside WSL.
- Do not move `.env`, `data/`, `runs/`, `reports/`, `output/`, or vector database artifacts into Git.
- Do not push directly from the root local repository unless a remote is deliberately configured later.

## Runtime Filesystem Rule

WSL benchmark work should happen inside the Linux filesystem, for example:

```bash
~/projects/Resourcepool_Gen
```

Avoid running long jobs from Windows-mounted paths such as:

```bash
/mnt/d/GEO-ALPHA/Resourcepool_Gen
```

The Windows-mounted path can reproduce the same file-lock and metadata friction this migration is meant to avoid.

## Module Design

### Core Parallel Runner Module

Create `scripts/full_api_parallel_runner.py`.

This module owns the platform-independent full API parallel execution Interface. Callers provide structured options, and the module runs or previews the benchmark.

Responsibilities:

- parse run mode and query count
- resolve selected model ids
- create run root, cache root, worker dirs, and merged dir
- copy or retarget seeded queries per model
- prepare worker Python argument files
- initialize `run_manifest.json`
- append `pipeline_state.jsonl` events
- write `ops_events.jsonl` events through direct `scripts.ops_logging` helper calls
- launch workers through a supplied platform adapter
- wait for worker exit-code files
- write `worker_exit_codes.json`
- call `scripts/full_api_run_status.py`
- call `scripts/merge_full_api_runs.py`
- render `progress.html`
- refresh `ops_summary.json`

This module should preserve the current command-line behavior of `scripts/run_full_api_parallel_with_watch.ps1`.

### Platform Adapter Module

Create `scripts/platform_runtime.py`.

This module should live outside `scripts/ui_app/` because both the UI execution layer and the core parallel runner need the same platform behavior.

The adapter Interface should expose:

- `platform_id`: `windows`, `linux`, or `wsl`
- `path_style`: `windows` or `posix`
- `python_executable`: usually `python` or `python3`
- `format_command(args: list[str]) -> str`
- `launch_worker(args, cwd, log_path) -> ProcessHandle`
- `launch_shell_command(command, cwd, log_path) -> ProcessHandle`
- `stop_process_tree(handle) -> StopResult`
- `is_parallel_api_command(command) -> bool`
- `is_guarded_pipeline_command(command) -> bool`

Concrete adapters:

- Windows adapter: uses PowerShell and `taskkill /PID <pid> /T /F`.
- POSIX adapter: uses `subprocess.Popen(args, start_new_session=True)` and stops with process-group termination.

WSL can use the POSIX adapter. It may include `platform_id = "wsl"` when `/proc/version` or environment signals indicate WSL, but it should not need a separate process model.

### Thin Entrypoints

Keep `scripts/run_full_api_parallel_with_watch.ps1` as a thin Windows wrapper.

Add `scripts/run_full_api_parallel_with_watch.sh` as a thin WSL/Linux wrapper.

Both should call the Python core runner with equivalent options. The wrappers should not reimplement worker orchestration, merge logic, or operations logging.

### UI Run Plan

Update `scripts/ui_app/run_plan.py` so command generation is platform-aware.

Expected behavior:

- Windows preview still shows PowerShell commands.
- WSL/Linux preview shows POSIX commands and slash paths.
- The API run command points at `python scripts/full_api_parallel_runner.py`.
- Pipeline steps use slash paths on WSL/Linux and backslash paths on Windows.
- No-op preview commands such as `REM Reuse data\processed and existing BM25 artifacts` get a POSIX equivalent such as `# Reuse data/processed and existing BM25 artifacts`.

The browser should still submit structured parameters. The server remains responsible for regenerating commands.

### UI Execution

Update `scripts/ui_app/execution.py` so launch, stop, and resume use platform adapters.

Launch manifests should add platform-aware fields while preserving current fields:

```json
{
  "status": "launched",
  "platform": "wsl",
  "pid": 1234,
  "process_group_id": 1234,
  "command": "python scripts/full_api_parallel_runner.py --run-mode test --models openai/gpt-4.1-mini --run-root runs/full_api_parallel_ui --run-stamp 20260526_230000",
  "monitor_run_root": "runs/full_api_parallel_ui/20260526_230000",
  "run_stamp": "20260526_230000"
}
```

Windows manifests can leave `process_group_id` empty or omit it. POSIX manifests should include it for reliable stop/resume.

Stop/resume rules remain unchanged at the safety level:

- stop resolves a known launch manifest by `monitor_run_root`
- stop does not accept a raw pid from the browser
- resume reuses the original trusted command from the launch manifest
- pipeline state receives an `interrupted`, `stop_failed`, or `running` event
- manifest status is updated after stop/resume attempts

### Operations Logging Contract

Do not change the phase-one operations event contract.

The WSL runner must write the same event types:

- `run_started`
- `run_completed`
- `stage_started`
- `stage_completed`
- `stage_failed`
- `api_failure`
- `worker_failed`
- `output_missing`
- `resume_started`
- `summary_generated`

The event `source` should identify the actual writer, for example:

- `scripts/full_api_parallel_runner.py`
- `scripts/run_full_api_parallel_with_watch.sh`
- `scripts/run_full_api_parallel_with_watch.ps1`

`ops_summary.json` remains an interpretation layer. Benchmark truth remains in pipeline state, worker exits, API attempts/events, and output artifacts.

### Git Publishing

Publishing should continue through the GitHub-backed `_publish/GEO_Benchmark_test` repository or through a fresh WSL clone of `HCGLHF/GEO_Benchmark_test.git`.

Recommended WSL publish flow:

1. Clone the GitHub repository inside WSL Linux storage.
2. Create branch `codex/wsl2-primary-runtime`.
3. Sync only safe source/docs/test files from the working tree.
4. Exclude `.env`, `data/`, `runs/`, `reports/`, `output/`, `vector_db/`, `.codex_runtime/`, caches, and local dependency directories.
5. Run the test suite or the approved subset.
6. Commit and push the branch.

This avoids Windows Git safe-directory and ownership friction in `_publish`.

## Error Handling

Worker failures:

- collect exit codes into `worker_exit_codes.json`
- classify outputs with `scripts/full_api_run_status.py`
- allow merge only when outputs are complete or complete with model warnings
- write `worker_failed` or `stage_failed` operations events for incomplete failures

Stop/resume:

- Windows uses process-tree termination.
- POSIX/WSL uses process-group termination.
- A force stop may interrupt one in-flight model call.
- Resume relies on persisted output rows and run-state files as the checkpoint.

Encoding:

- New WSL logs should be UTF-8.
- Existing monitor decoding should keep UTF-16 detection for historical Windows worker logs.

Stale summaries:

- `ops_summary.json` can be regenerated with `python scripts/ops_logs.py doctor --run-root <run>`.
- Run Monitor should keep live-health fallback when the summary is stale.

## Testing Strategy

Windows-side tests in the current workspace:

- existing logger and monitor tests stay green
- new tests for platform command rendering
- new tests for POSIX launch metadata using fake `Popen`
- new tests for POSIX stop using fake process runner or signal helper
- existing Windows PowerShell tests remain green
- UI run plan tests assert both Windows and WSL command previews
- UI execution tests assert both `taskkill` and process-group stop behavior

WSL manual verification:

```bash
cd ~/projects/Resourcepool_Gen
python -m pytest tests/test_ops_logging.py tests/test_ops_logs_cli.py tests/test_run_pipeline_step.py -q
python -m pytest tests/test_ui_run_plan.py tests/test_ui_execution.py tests/test_ui_run_monitor.py -q
python -m pytest tests/test_full_api_run_status.py -q
bash scripts/run_full_api_parallel_with_watch.sh --run-mode test --models openai/gpt-4.1-mini --dry-run
```

Optional WSL chain check, only when API keys and credits are intentionally available:

```bash
bash scripts/run_full_api_parallel_with_watch.sh --run-mode test --models openai/gpt-4.1-mini
python scripts/ops_logs.py doctor --run-root runs/full_api_parallel/<timestamp>
```

The final external API check must remain explicit because it can send retrieved corpus excerpts to external model providers and consume credits.

## Rollout Plan

1. Add the platform adapter tests and module.
2. Add the Python core runner with dry-run parity against the current PowerShell runner.
3. Convert the PowerShell runner into a thin wrapper.
4. Add the Bash wrapper.
5. Update UI run planning to use platform-aware commands.
6. Update UI launch/stop/resume to use platform adapters.
7. Update Run Monitor docs and WSL runbook.
8. Add ADR 0002 for WSL2 as the primary runtime.
9. Sync safe files to the publish repository or WSL clone.
10. Push branch `codex/wsl2-primary-runtime`.

## Open Constraints

- Codex currently cannot see the user's Ubuntu WSL2 distro because this process runs under a different Windows user.
- Real WSL validation should be done by the user inside Ubuntu unless Codex is later attached to the same WSL context.
- The user's temporary WSL password should be changed later with `passwd`; it is not a migration blocker.

## Acceptance Criteria

- Windows tests for current behavior still pass.
- Platform adapter tests cover Windows and POSIX behavior.
- The Python core runner can produce a dry-run plan equivalent to the current PowerShell runner.
- WSL/Linux dry-run uses POSIX paths and does not require PowerShell.
- WSL/Linux stop/resume uses process-group metadata from the launch manifest.
- `pipeline_state.jsonl`, `run_manifest.json`, `ops_events.jsonl`, `ops_summary.json`, `worker_exit_codes.json`, `progress.html`, and `merged/competitive_gap_report.md` keep their existing meanings.
- WSL runbook clearly tells users to run from Linux storage, not `/mnt/d`.
- A safe publish branch named `codex/wsl2-primary-runtime` can be pushed without committing local data or secrets.
