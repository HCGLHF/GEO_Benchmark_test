# Run Full API Client Acquisition Evaluation

This is the highest-fidelity run path. It calls the configured external LLM APIs and sends retrieved corpus excerpts to the model provider for reranking and answer generation.

Use this only from your own local PowerShell terminal, not through Codex tool execution.

## Before Running

Confirm `.env` contains:

```text
OPENROUTER_API_KEY=your_key_here
```

The script reads `.env` automatically.

## Full Run

From `D:\GEO-ALPHA\Resourcepool_Gen`:

```powershell
python scripts\run_full_api_client_acquisition.py --config config\client_acquisition_simulator.yaml
```

This uses the config default of 200 queries per model.

## Recommended Run Without Doubao Pro

OpenRouter previously returned `400 Bad Request` for `bytedance-seed/seed-2.0-pro`. To run the other four models:

```powershell
python scripts\run_full_api_client_acquisition.py --config config\client_acquisition_simulator.yaml --exclude-model bytedance-seed/seed-2.0-pro
```

## Smaller Smoke Run

Use this to verify the API key and provider behavior before spending on the full run:

```powershell
python scripts\run_full_api_client_acquisition.py --config config\client_acquisition_simulator.yaml --queries-per-model 5 --exclude-model bytedance-seed/seed-2.0-pro
```

## Outputs

Each run creates a timestamped directory:

```text
runs/client_acquisition_simulator_full_api_YYYYMMDD_HHMMSS/
```

Important files:

- `competitive_gap_report.md`
- `brand_performance_by_model.csv`
- `dimension_breakdown.csv`
- `retrieval_by_model.csv`
- `retrieval_evidence_by_model.jsonl`
- `model_answer_evaluations.csv`
- `api_call_summary.csv`
- `run_config.resolved.json`

## Notes

- The run uses a clean two-message model context for each API call.
- The model-specific scenario generation, rerank, and answer steps remain isolated by model.
- The global LLM cache is still enabled. Because the corpus hash changed after resource expansion, stale cached responses from the old corpus should not be reused.
- A per-run `run_state.sqlite` is created inside the timestamped run directory.
