# Single-Model Parallel Full API Runs

Use this mode for the next highest-fidelity run. It opens one PowerShell process per model, so the models run in parallel instead of waiting for each other.

Do not use this to modify a run that is already in progress. Let the current run finish.

## Start Parallel Runs

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
