# API Run Observability Engineering Plan

## Goal

Make full API benchmark runs easier to diagnose while keeping model execution explicit and file-based.

## Scope

- Add a chain health summary for active runs.
- Show API-call progress bars in the local UI for each model worker.
- Add a low-cost `test` run mode for link-checking the full API path.

## Design

The API runner remains the execution boundary. `scripts/run_full_api_parallel_with_watch.ps1` launches workers, `scripts/run_full_api_client_acquisition.py` runs one model, and `scripts/geo_eval/orchestrator.py` records model-call facts.

Monitoring stays read-only. `scripts/ui_app/run_monitor.py` reads existing run files and computes health status from facts:

- pipeline events from `pipeline_state.jsonl`
- model attempts from `api_orchestrator_attempts.jsonl`
- in-flight API events from `api_call_events.jsonl`
- worker process outcomes from `worker_exit_code.txt`
- recent logs from `worker.log`

The UI renders this health object and per-model progress bars without making control decisions.

## Test Mode

`test` mode is for checking whether the API chain works, not for measuring ranking. It defaults to two seeded queries per model, which normally produces four external model calls per model because each seeded query uses one rerank call and one answer call. This keeps the run under the user's requested five-call class while preserving both critical API stages.

If scenarios are regenerated instead of seeded, scenario-generation calls are additional and the UI warns that the run is no longer a minimal chain test.

## Files

- `scripts/run_full_api_parallel_with_watch.ps1`: add `test` run mode.
- `scripts/ui_app/run_plan.py`: map UI `test` to the low-cost query count and warnings.
- `scripts/ui_app/run_monitor.py`: compute health and per-model API progress.
- `scripts/ui_app/server.py`: render health and progress bars.
- `scripts/geo_eval/orchestrator.py`: write API call event logs for started/completed/error/cache-hit calls.
- Tests under `tests/` cover the new contracts.

