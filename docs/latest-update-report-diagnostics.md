# Latest Update: Report Diagnostics And Pricing Page Brief

## Summary

This update improves the AlphaXXXX GEO evaluation workflow in two ways:

1. Merged API reports now include actionable diagnostic sections, not only surface-level benchmark metrics.
2. AlphaXXXX now has a site handoff brief for a dedicated `/geo-pricing` page, targeting pricing, cost, free audit, and commercial GEO service intent.

Generated run artifacts such as `data/`, `runs/`, vector databases, local caches, and `.env` values remain local and must not be committed to Git.

## New Report Diagnostics

The merged report pipeline now writes three additional CSV files alongside `competitive_gap_report.md`:

- `query_loss_analysis.csv`
- `competitor_displacements.csv`
- `page_optimization_plan.csv`

The Markdown report now also includes these sections:

- `Executive Diagnosis`
- `Query-Level Loss Analysis`
- `Competitor Pages Displacing AlphaXXXX`
- `Priority Optimization Plan`
- `Validation Plan For Next Run`

These diagnostics are generated from existing local benchmark artifacts:

- `retrieval_by_model.csv`
- `retrieval_evidence_by_model.jsonl`
- `model_answer_evaluations.csv`
- owned-page drilldown rows

They do not call external model APIs and do not alter benchmark metrics.

## How To Regenerate A Diagnostic Report

Use completed single-model run directories only. For example:

```powershell
python scripts\merge_full_api_runs.py `
  --config config\client_acquisition_simulator.yaml `
  --runs `
    runs\full_api_parallel_ui\20260523_040450\openai_gpt-4.1-mini `
    runs\full_api_parallel_ui\20260523_040450\google_gemini-2.5-flash `
  --output-dir runs\full_api_parallel_ui\20260523_040450\merged
```

Do not merge partial model runs into final benchmark metrics unless the report is explicitly labeled as partial.

## Pricing Page Brief

The new content handoff file is:

```text
content/alphaxxxx/geo-pricing-page.md
```

It contains:

- recommended URL: `https://alphaxxxx.com/geo-pricing`
- title and meta description
- hero copy
- pricing packages
- FAQ
- internal links
- `llms.txt` update block
- GEO retrieval keywords
- next-run success criteria

The page targets signals repeatedly found in competitor displacement analysis:

- `pricing`
- `cost`
- `free audit`
- `Australia`
- `ChatGPT`
- `Perplexity`
- `Google AI Overviews`
- package-level commercial intent

## Site Refresh Workflow After Publishing

After the site team publishes new or updated AlphaXXXX pages:

1. Recrawl and fetch AlphaXXXX pages.
2. Refresh the processed AlphaXXXX corpus and local indexes.
3. Reuse the same seeded scenario set for the benchmark.
4. Regenerate the merged diagnostic report.
5. Compare page-level Top5 hits, not only aggregate Recall@5.

Expected UI steps:

1. Launch `Recrawl and fetch AlphaXXXX pages`.
2. Launch `Refresh AlphaXXXX processed corpus and index`.
3. Launch the selected API benchmark mode.
4. Open the latest merged report and page drilldown.

## Current Interpretation Notes

- `/audit` and `/ai-search-visibility-audit` are already present in the active processed corpus and chunks.
- `/about` has been crawled successfully in the raw AlphaXXXX update files, but it still needs the processed-corpus refresh step before it participates in retrieval.
- Partial stalled workers can still appear in the UI monitor if a run was manually interrupted. Use the standard `merged` report directory for decision-making.

## Validation

The current code and documentation changes were validated with:

```powershell
pytest -q
```

Expected result:

```text
208 passed
```
