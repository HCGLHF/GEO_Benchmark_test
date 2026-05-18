# Single-Model Parallel Full API Runs

Use this mode for the next highest-fidelity run. It opens one PowerShell process per model, so the models run in parallel instead of waiting for each other.

Do not use this to modify a run that is already in progress. Let the current run finish.

## Recommended One-Command Run

From `D:\GEO-ALPHA\Resourcepool_Gen`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_api_parallel_with_watch.ps1 -QueriesPerModel 200
```

This command:

- opens one worker process per model
- gives every model its own output directory
- gives every model its own LLM cache SQLite file to avoid cache lock contention
- refreshes progress with `scripts\watch_full_api_run.py`
- automatically runs `scripts\merge_full_api_runs.py` when every worker exits successfully
- prints the merged `competitive_gap_report.md` path

Before a real paid/API run, preview the exact commands without starting workers:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_api_parallel_with_watch.ps1 -QueriesPerModel 200 -DryRun
```

To include Doubao:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_api_parallel_with_watch.ps1 -QueriesPerModel 200 -IncludeDoubao
```

Doubao Pro is excluded by default because OpenRouter previously returned errors for the requested model id.

To skip automatic merge and merge manually later:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_full_api_parallel_with_watch.ps1 -QueriesPerModel 200 -SkipMerge
```

## Start Parallel Runs

The older launcher is still available if you only want to start workers and merge manually.

From `D:\GEO-ALPHA\Resourcepool_Gen`:

```powershell
.\scripts\run_full_api_parallel.ps1 -QueriesPerModel 200
```

By default this runs:

- `openai/gpt-4.1-mini`
- `google/gemini-2.5-flash`
- `perplexity/sonar-pro`
- `deepseek/deepseek-chat`

Doubao Pro is excluded by default because OpenRouter previously returned `400 Bad Request`.

To include Doubao:

```powershell
.\scripts\run_full_api_parallel.ps1 -QueriesPerModel 200 -IncludeDoubao
```

## Smoke Test

```powershell
.\scripts\run_full_api_parallel.ps1 -QueriesPerModel 5
```

## Merge Finished Runs

The launcher prints the merge command after starting the model processes.

It will look like:

```powershell
python scripts\merge_full_api_runs.py --config config\client_acquisition_simulator.yaml --runs runs\full_api_parallel\YYYYMMDD_HHMMSS\openai_gpt-4.1-mini runs\full_api_parallel\YYYYMMDD_HHMMSS\google_gemini-2.5-flash runs\full_api_parallel\YYYYMMDD_HHMMSS\perplexity_sonar-pro runs\full_api_parallel\YYYYMMDD_HHMMSS\deepseek_deepseek-chat --output-dir runs\full_api_parallel\YYYYMMDD_HHMMSS\merged
```

The merged output includes:

- `competitive_gap_report.md`
- `brand_performance_by_model.csv`
- `dimension_breakdown.csv`
- `retrieval_by_model.csv`
- `retrieval_evidence_by_model.jsonl`
- `model_answer_evaluations.csv`
- `api_call_summary.csv`
- `merge_manifest.json`
