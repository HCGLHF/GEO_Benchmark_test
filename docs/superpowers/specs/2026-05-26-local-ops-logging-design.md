# Local Operations Logging Design

## Goal

Make local GEO benchmark and corpus pipeline runs easy to maintain and diagnose over time without replacing the existing file-based run contracts.

The first phase focuses on local stable troubleshooting. Each run remains self-contained under its run root, while a small operations layer gives the user one reliable place to answer:

- Is this run healthy?
- What failed or looks suspicious?
- Which files should I inspect next?
- Is the run safe to interpret, resume, or rerun?

## Decision

Use the existing run directory as the operations boundary and add two files per run root:

- `ops_events.jsonl`: append-only structured operations events for important lifecycle and troubleshooting facts.
- `ops_summary.json`: current human-readable health summary generated from existing run facts and operations events.

This keeps the current facts authoritative:

- `run_manifest.json`
- `pipeline_state.jsonl`
- `worker.log`
- `worker_exit_code.txt`
- `api_call_events.jsonl`
- `api_orchestrator_attempts.jsonl`
- run output CSV/JSONL artifacts

The operations layer summarizes and links these facts. It does not replace them, mutate benchmark outputs, or become a hidden execution controller.

## Non-Goals

- No cloud logging in phase one.
- No push alerts, email alerts, or webhook alerts.
- No global log database in phase one.
- No automatic deletion of large run artifacts.
- No broad rewrite of every existing script from `print()` to Python `logging`.
- No change to benchmark metrics, merge rules, or report calculations.

## Architecture

Add a small Python operations logging boundary:

- `scripts/ops_logging.py`: writes structured events and generates summaries from known run facts.
- `scripts/ops_logs.py`: command-line inspection tool for summaries, events, and diagnostics.

Integrate only the critical paths in phase one:

- `scripts/run_pipeline_step.py`: write operations events for pipeline stage start, completion, and failure.
- `scripts/geo_eval/orchestrator.py`: write operations events for external API failures while preserving existing API event files.
- `scripts/run_full_api_parallel_with_watch.ps1`: call the Python operations helper for run lifecycle, worker failure, merge, and report outcomes.
- `scripts/ui_app/run_monitor.py`: read `ops_summary.json` first, then fall back to existing health inference when the summary is missing.

This lightly absorbs the useful part of standard logging: new code records structured levels and event types instead of adding more free-form output. Existing text logs remain useful as detail sources.

## Event Contract

`ops_events.jsonl` contains one JSON object per line. Required fields:

```json
{
  "created_at": "2026-05-26T10:12:30Z",
  "level": "info",
  "event_type": "stage_started",
  "run_root": "runs/full_api_parallel_ui/20260525_214431",
  "stage": "answer",
  "model": "openai/gpt-4.1-mini",
  "message": "Answer generation started.",
  "details": {
    "queries": 50,
    "expected_api_calls": 50
  },
  "source": "scripts/run_full_api_parallel_with_watch.ps1"
}
```

Field rules:

- `created_at`: UTC ISO timestamp.
- `level`: one of `debug`, `info`, `warning`, or `error`.
- `event_type`: one of the stable phase-one event types.
- `run_root`: relative or absolute run root supplied by the caller.
- `stage`: pipeline stage name when known, otherwise an empty string.
- `model`: model id or safe model directory name when known, otherwise an empty string.
- `message`: concise human-readable explanation.
- `details`: JSON object for structured metadata.
- `source`: script or module that wrote the event.

Phase-one `event_type` values:

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

Unknown or experimental events should use existing types with richer `details` instead of expanding the enum casually.

## Health Summary Contract

`ops_summary.json` is optimized for fast human troubleshooting:

```json
{
  "status": "warning",
  "run_root": "runs/full_api_parallel_ui/20260525_214431",
  "current_stage": "answer",
  "updated_at": "2026-05-26T10:15:00Z",
  "issues": [
    "qwen_qwen3.7-max had rate-limit failures; outputs are complete but should be interpreted with caution."
  ],
  "recommended_actions": [
    "Review api_call_summary.csv for the affected model.",
    "Use Run Monitor before deciding whether to resume."
  ],
  "key_files": {
    "pipeline_state": "pipeline_state.jsonl",
    "ops_events": "ops_events.jsonl",
    "worker_logs": [
      "openai_gpt-4.1-mini/worker.log"
    ],
    "api_summary": "merged/api_call_summary.csv"
  }
}
```

Status values:

- `ok`: no detected issue; running or completed facts are consistent.
- `warning`: recoverable issue or caution; examples include rate limits with complete outputs or parent pipeline warnings.
- `error`: failed worker, failed critical stage, or missing required outputs.
- `stalled`: no recent useful progress where progress is expected.
- `unknown`: not enough facts exist to classify the run.

The summary should include stable relative paths when possible so users can move or archive a run directory without breaking the meaning of the summary.

## Summary Generation Rules

The summary generator reads existing files and operations events in this priority order:

1. `pipeline_state.jsonl` for stage state and current stage.
2. Per-model `worker_exit_code.txt` for worker process outcomes.
3. Per-model `api_orchestrator_attempts.jsonl` and `api_call_summary.csv` for API failures.
4. Expected output files such as `retrieval_by_model.csv`, `model_answer_evaluations.csv`, and merged report artifacts.
5. `ops_events.jsonl` for explicit lifecycle and failure events.
6. `worker.log` and pipeline `logs/*.log` only as tail text for humans, not as the primary structured source.

The generator must not call external APIs, rerun benchmark steps, modify benchmark metrics, or change pipeline state.

Recommended actions should be deterministic and conservative:

- `402 Payment Required`: stop, add credit, then resume from the known UI launch when applicable.
- `429` or rate limit: wait/back off, then resume from existing outputs.
- Missing retrieval rows: inspect rerank stage and per-model worker log.
- Missing answer rows: inspect answer stage and API failures.
- Non-zero worker exit with complete outputs: interpret with caution and check the model warning.
- Non-zero worker exit with incomplete outputs: do not merge into decision metrics.

## UI Behavior

`scripts/ui_app/run_monitor.py` should prefer `ops_summary.json` when it exists:

- `chain health` displays `ops_summary.status`.
- The log panel starts with summary issues and recommended actions.
- Existing pipeline log tails and worker log tails remain visible.
- Existing fallback health inference remains active when `ops_summary.json` is missing.

The local UI should not gain a new global operations dashboard in phase one. The Run Monitor stays focused on the selected run root.

## CLI Behavior

Add `scripts/ops_logs.py` with three phase-one commands:

```powershell
python scripts\ops_logs.py summary --run-root runs\full_api_parallel_ui\20260525_214431
python scripts\ops_logs.py events --run-root runs\full_api_parallel_ui\20260525_214431 --level error
python scripts\ops_logs.py doctor --run-root runs\full_api_parallel_ui\20260525_214431
```

Command behavior:

- `summary`: print `ops_summary.json`; if missing, generate it from current facts and then print it.
- `events`: filter `ops_events.jsonl` by `--level`, `--event-type`, and `--model`.
- `doctor`: regenerate `ops_summary.json`, print status, issues, recommended actions, and key files.

The CLI should return a non-zero exit code only for command misuse or unreadable run roots. A run with `status=error` is an operational finding, not a CLI crash.

## Retention and Cleanup

Phase one should provide visibility before deletion:

- Add dry-run cleanup support only after summaries and events are stable.
- Cleanup should report candidate run directories by age, size, status, and last update.
- Cleanup must not delete by default.
- Cleanup must not remove `.env`, configs, processed corpus files, or current run roots.

Default guidance for local maintenance:

- Keep the latest 30 run roots or the last 30 days of run roots.
- Archive important `merged/` reports before removing old raw worker outputs.
- Prefer deleting entire old run roots over deleting individual files inside a run root.

## Testing

Phase-one tests should cover:

- Writing valid `ops_events.jsonl` records with stable fields.
- Filtering events by level, event type, and model.
- Generating `ops_summary.json` from a healthy completed run.
- Generating `warning` for API rate limits with complete outputs.
- Generating `error` for failed workers with incomplete outputs.
- Generating `stalled` from stale progress facts when expected outputs are incomplete.
- UI monitor preference for `ops_summary.json` with fallback to existing health inference.
- `run_pipeline_step.py` still writes `pipeline_state.jsonl` and now also writes operations events.

Existing monitor tests should remain valid because the operations layer is additive.

## Rollout

Implement in small steps:

1. Add `scripts/ops_logging.py` and focused tests.
2. Add `scripts/ops_logs.py` and focused CLI tests.
3. Integrate `run_pipeline_step.py`.
4. Integrate API failure logging in `scripts/geo_eval/orchestrator.py`.
5. Integrate key lifecycle calls from `scripts/run_full_api_parallel_with_watch.ps1`.
6. Update `scripts/ui_app/run_monitor.py` to prefer summaries.
7. Update docs for local maintenance and troubleshooting.

Each step should preserve existing file contracts and keep current Run Monitor behavior usable if no operations files exist.
