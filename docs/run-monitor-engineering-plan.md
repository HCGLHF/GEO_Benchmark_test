# Run Monitor Engineering Plan

## Goal

Expose the full GEO benchmark lifecycle in the local UI without hiding API/AWS execution behind the dashboard. The monitor should make long runs understandable: current stage, per-model progress, API calls, failures, logs, report metrics, and next action.

## Staged Design

### Phase 1: Read-Only Monitor

Implemented first because it has the least operational risk.

- Read parallel run roots such as `runs/full_api_parallel_ui/<timestamp>`.
- Summarize each model worker with `scripts/watch_full_api_run.py` contracts.
- Show current stage: scenario generation, rerank, answer, merge/report, complete, or stalled.
- Show API calls, cache hits, failures, missing rows, answer rows, and worker log tails.
- Read merged report metrics when `merged/` exists.
- Read `run_manifest.json` and `pipeline_state.jsonl` when they exist, so pre-API stages and API stages share one status contract.

### Phase 2: Exact Model Runs

The parallel runner now accepts exact model subsets:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_full_api_parallel_with_watch.ps1 `
  -RunMode quick `
  -Models "openai/gpt-4.1-mini,google/gemini-3.5-flash" `
  -SeedQueriesRunDir runs\client_acquisition_simulator_full_api_20260517_200716
```

This makes UI model checkboxes honest: selected models map directly to worker processes.

### Phase 3: Guarded Execution

Add execution only after read-only monitoring is stable.

- Show command preview before launch.
- Require a one-click confirmation inside the UI.
- Start local processes with one run root per launch.
- Stream logs from files instead of holding subprocess stdout in memory.
- Keep stop/resume as explicit commands, not hidden automatic retries.
- Run crawl, clean, chunk, index, AWS sync, and other shell stages through `scripts/run_pipeline_step.py` so every step appends running/completed/failed events to `pipeline_state.jsonl`.

Current implementation:

- `/api/launch-run` starts only the backend-generated parallel API benchmark command.
- `/api/launch-stage` starts only backend-generated non-API commands that begin with `python scripts\run_pipeline_step.py`.
- The UI must send `confirmed=1`; otherwise the endpoint returns a confirmation preview and does not create launch files.
- A successful launch writes `runs/ui_launches/<timestamp>/launch_manifest.json` and `launch.log`.
- The launch response includes `monitor_run_root`, which the UI copies into Run Monitor.
- The UI exposes a pipeline-step selector populated only from guarded `run_pipeline_step.py` commands in the current plan.

Remaining work:

- Add process lifecycle controls for stop/resume.
- Add richer log streaming and launch history.

### Pipeline State Contract

Each run root may contain:

- `run_manifest.json`: run type, model list, ordered stage list, metadata, created/updated timestamps.
- `pipeline_state.jsonl`: append-only stage events with `stage`, `status`, `message`, optional `model`, optional `details`, and `created_at`.

The canonical stage names for the UI are:

```text
crawl / clean / chunk / index / AWS sync / scenario_generation / rerank / answer / merge / report
```

For one-off commands, use:

```powershell
python scripts\run_pipeline_step.py --run-root runs\ui_pipeline\<timestamp> --stage clean -- python scripts\clean_documents.py
```

### Phase 4: Report Drilldown

Add report surfaces after merged outputs exist:

- AlphaXXXX overall rank.
- Brands above AlphaXXXX.
- Recall@5 / Top10 / Mention Rate / Citation Rate.
- Model split.
- Persona and journey-stage split.
- Retrieved AlphaXXXX URLs.
- Weak pages and content recommendations.

## Boundaries

- Monitor modules are read-only.
- Runner modules start or resume runs.
- Report modules aggregate completed run outputs.
- UI modules call these boundaries but do not reimplement crawler, evaluator, or cloud logic.
- Pipeline state files are append-only facts; monitors read them, while runners/wrappers write them.

## Risks

- Stop can leave child Python processes alive if it only kills the PowerShell wrapper.
- Resume must reuse the same output directory intentionally; clean reruns should use a new run root.
- Partial reports should be clearly labeled and not merged into decision metrics.
- UI execution must never send corpus excerpts to third-party APIs without an explicit user action.
- A command that bypasses `run_pipeline_step.py` will not produce pre-API stage state unless the script writes events directly.
