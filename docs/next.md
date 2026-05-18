# Next

## Done

- Synchronized the current source, tests, configuration, and architecture memory into the GitHub-backed `_publish/GEO_Benchmark_test` repository.
- Completed pre-push validation for the publish repository.
- Created project memory and architecture self-check files.
- Recorded the requirement to read memory, architecture, risk, next-step, and ADR files before future code changes.
- Added the first ADR for persistent project memory and architecture self-check.

## Learned

- The active workspace root is not itself a git repository; the publishable repository is `_publish/GEO_Benchmark_test`.
- The GitHub CLI is not installed in this environment, so this publish uses direct `git` commands instead of a PR workflow.
- The project now has an explicit rule that every development task must preserve engineering memory, architecture boundaries, and next-step judgment.
- Full API realism remains operationally useful but must be run by the user locally when it sends corpus excerpts to third-party APIs.

## Risks

- Publishing must continue to avoid local `.env`, `data/`, `runs/`, `reports/`, `output/`, and vector database artifacts.
- Direct push to `main` has less review ceremony than a PR, so each publish needs an explicit local audit.
- Future changes may accidentally skip this memory check unless it is treated as part of the normal development entry routine.
- Existing scripts are useful but some paths still need better streaming, resume, and monitoring behavior for long full API runs.

## Next

1. Add a lightweight `watch_full_api_run.py` monitor for long API runs.
2. Improve full API output streaming so rerank and answer rows are written incrementally.
3. Add a short release checklist for future direct pushes when `gh` is unavailable.
