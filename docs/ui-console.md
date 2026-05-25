# Local UI Console

The local UI console is a project dashboard plus guarded run launcher. It does not accept arbitrary shell commands, and cost-bearing API or cloud actions still require explicit user confirmation.

Start it from the project root:

```powershell
python -m scripts.ui_app.server --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

## Current Capabilities

- Shows local resource-library counts for companies, URLs, documents, chunks, and AlphaXXXX rows.
- Shows current competitors from `config/sources.yaml` and `config/client_acquisition_simulator.yaml`.
- Shows configured evaluation models.
- Shows latest merged report summary when a merged report exists under `runs/`.
- Shows historical merged reports from `runs/**/merged*/competitive_gap_report.md`, with AlphaXXXX rank, Top5 share, mention rate, answer count, and an in-UI Markdown preview.
- Shows owned-page drilldowns for the selected report: which AlphaXXXX URLs entered retrieval Top5 and which owned pages are weakest or never entered Top5.
- Shows non-secret cloud configuration presence from environment variables.
- Builds dry-run commands for owned-site recrawl/fetch, owned-site processed corpus replacement, optional AWS sync, and API benchmark execution.
- Monitors a parallel run root with current stage, per-model progress, API calls, failure counts, log tails, and merged report status.
- Shows chain health for API runs, including failed workers, API failures, missing outputs, and likely stalls.
- Shows targeted 402 payment-required and 429 rate-limit guidance so interrupted runs can be stopped and resumed deliberately.
- Shows pipeline-stage status, pipeline log tails, and recrawl/fetch progress bars from `run_manifest.json`, `pipeline_state.jsonl`, and `logs/*.log` when a run root has them.
- Shows local operations summaries from `ops_summary.json` when present, including health status, issues, recommended actions, and key files.
- Preserves detailed troubleshooting through `ops_events.jsonl`, pipeline log tails, worker log tails, and API attempt files under the selected run root.
- Can launch the backend-generated parallel API benchmark after an explicit browser confirmation.
- Can stop or resume a UI-launched API benchmark from Run Monitor after explicit browser confirmation.
- Can launch backend-generated guarded pipeline steps such as owned-site recrawl/fetch, clean, chunk, index, and AWS sync after an explicit browser confirmation.

## Local Operations Logs

Each monitored run root may contain:

- `ops_events.jsonl`: structured operations events such as run start, stage failure, API failure, worker failure, and summary generation.
- `ops_summary.json`: current local health summary with issues, recommended actions, and key files.

Useful commands:

```powershell
python scripts\ops_logs.py summary --run-root runs\full_api_parallel_ui\<timestamp>
python scripts\ops_logs.py events --run-root runs\full_api_parallel_ui\<timestamp> --level error
python scripts\ops_logs.py doctor --run-root runs\full_api_parallel_ui\<timestamp>
```

## Boundaries

- The UI does not run paid crawler fallback in the default owned-site recrawl/fetch step.
- The UI can launch model API calls or AWS/RDS writes only through generated commands after explicit confirmation.
- The UI can mutate local raw/processed corpus files only through generated pipeline steps after explicit confirmation.
- Real runs still use the existing scripts after the user reviews the generated command plan.
- Run Monitor status remains file-based, while stop/resume is a guarded execution path that only works for API runs launched through this UI.
- Pre-API stages should use `scripts/run_pipeline_step.py` if they need to appear in Run Monitor.
- The launch button only starts the generated API benchmark command; it does not execute arbitrary user-provided shell strings.
- The step launch button only starts commands generated from the current run plan that are wrapped by `scripts/run_pipeline_step.py`.
- Report preview reads only known completed report directories under `runs/`; it does not expose arbitrary local files.
- Page drilldown reads only known completed report directories under `runs/`; it uses `owned_top5_pages.csv` and `owned_weak_pages.csv` when present, or computes them from `retrieval_evidence_by_model.jsonl` plus `data/processed/documents.jsonl`.

## Next UI Work

1. Add launch history and richer log streaming.
2. Add retry/backoff tuning for 429-heavy model workers before they require manual stop/resume.
3. Add deeper persona/stage weak-page grouping and URL-level content optimization suggestions.
