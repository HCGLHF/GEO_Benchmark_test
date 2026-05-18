# Next

## Done

- Added `scripts/run_full_api_parallel_with_watch.ps1` for one-command single-model parallel full API runs.
- Added `--cache-path` support to `scripts/run_full_api_client_acquisition.py` so parallel model workers can use independent SQLite caches.
- Documented the watched parallel run command in project memory and the parallel full API run guide.
- Added a read-only `scripts/watch_full_api_run.py` monitor for full API runs.
- Added tests for monitor aggregation, missing files, stalled runs, text formatting, and latest-run discovery.
- Verified the monitor against the existing `client_acquisition_simulator_full_api_20260517_200716` run.
- Prepared the monitor script, tests, architecture note, and plan for upload to the GitHub-backed publish repository.
- Synchronized the current source, tests, configuration, and architecture memory into the GitHub-backed `_publish/GEO_Benchmark_test` repository.
- Completed pre-push validation for the publish repository.
- Created project memory and architecture self-check files.
- Recorded the requirement to read memory, architecture, risk, next-step, and ADR files before future code changes.
- Added the first ADR for persistent project memory and architecture self-check.

## Learned

- The active workspace root is not itself a git repository; the publishable repository is `_publish/GEO_Benchmark_test`.
- The GitHub CLI is not installed in this environment, so this publish uses direct `git` commands instead of a PR workflow.
- The existing full API run has complete orchestrator attempts, so the monitor can report exact 1660/1660 completion from existing artifacts.
- One-command parallel execution is safest when each model gets its own output directory, run-state SQLite, and LLM cache SQLite.
- The project now has an explicit rule that every development task must preserve engineering memory, architecture boundaries, and next-step judgment.
- Full API realism remains operationally useful but must be run by the user locally when it sends corpus excerpts to third-party APIs.

## Risks

- Publishing must continue to avoid local `.env`, `data/`, `runs/`, `reports/`, `output/`, and vector database artifacts.
- Direct push to `main` has less review ceremony than a PR, so each publish needs an explicit local audit.
- Future changes may accidentally skip this memory check unless it is treated as part of the normal development entry routine.
- Existing scripts are useful but some paths still need better streaming and resume behavior for long full API runs.
- The monitor reports from files that already exist; it cannot see in-flight API calls before the runner writes an attempt row.
- Parallel API execution can hit provider rate limits faster than serial execution, so failed model workers should be inspected before merge.

## Next

1. Improve full API output streaming so rerank and answer rows are written incrementally.
2. Add a short release checklist for future direct pushes when `gh` is unavailable.
3. Use `scripts/run_full_api_parallel_with_watch.ps1 -QueriesPerModel 200` for the next full API benchmark after AlphaXXXX content expansion.
