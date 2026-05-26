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
