# Architecture

## Modules

- `scripts/discover_site_urls.py`: discovers same-site URLs from seeds, sitemaps, robots, and links.
- `scripts/crawl_pages.py` and `scripts/crawl_pages_parallel.py`: tiered page fetchers using `httpx`, Playwright, and optional paid fallback.
- `scripts/clean_documents.py`: converts raw pages into document records with brand metadata.
- `scripts/chunk_documents.py`: splits documents into retrieval chunks.
- `scripts/build_keyword_index.py`: builds the local BM25-style keyword artifact.
- `scripts/build_vector_index.py`: builds the local Qdrant vector index.
- `scripts/client_acquisition_simulator.py`: orchestrates scenario generation, retrieval, rerank, answers, brand metrics, competitive reports, incremental run-output writes, and resume skipping for completed rows.
- `scripts/run_full_api_client_acquisition.py`: user-run entrypoint for highest-fidelity external API evaluation.
- `scripts/run_full_api_parallel_with_watch.ps1`: one-command local orchestrator that launches one full API worker per model, supports `quick` and `standard` run modes, monitors each run, and merges successful outputs.
- `scripts/seed_api_queries.py`: copies a bounded set of existing API-generated scenario queries into a single-model run directory so refreshed-corpus runs can skip scenario generation.
- `scripts/watch_full_api_run.py`: read-only monitor for long full API runs, summarizing progress and missing rows from run output files without calling model APIs.
- `scripts/render_full_api_progress_html.py`: renders a static auto-refreshing HTML dashboard from full API run output files.
- `scripts/merge_full_api_runs.py`: merges single-model runs into one report.
- `scripts/alphaxxxx_llms_router.py`: generates the AlphaXXXX `llms.txt` intent router used to direct AI crawlers and retrieval toward the strongest canonical pages.
- `scripts/build_corpus_variant.py`: builds evaluation corpus variants, currently `without_llms`, from processed artifacts without mutating the main corpus.
- `scripts/compare_llms_ab_reports.py`: compares with-`llms.txt` and without-`llms.txt` merged benchmark reports for target-brand lift.
- `scripts/cloud/config.py`: loads required cloud environment variables for explicit S3/RDS operations without exposing secrets in committed files.
- `scripts/cloud/corpus_quality.py`: audits inventory, documents, and chunks before cloud import, blocking unsafe corpus versions with duplicate IDs, orphan chunks, missing fields, or mojibake markers.
- `scripts/cloud/import_corpus.py`: plans and executes the first cloud import path for URL inventory, processed documents, processed chunks, S3 artifact records, and PostgreSQL core corpus rows.
- `scripts/cloud/qdrant_snapshot.py`: packages the local Qdrant directory as a rebuildable S3 artifact and registers it in PostgreSQL.
- `scripts/cloud/verify_cloud_import.py`: verifies an imported cloud corpus version by comparing PostgreSQL corpus counts with S3 artifact object sizes.
- `scripts/cloud/s3_artifacts.py`: computes stable S3 object keys, hashes local artifacts, and uploads snapshots when an import is executed.
- `scripts/cloud/postgres.py`: applies the PostgreSQL schema and upserts the core corpus into RDS using lazy `psycopg` imports so normal local tests do not require cloud dependencies.
- `scripts/ui_app/corpus_summary.py`: reads local inventory, documents, and chunks to summarize resource-library size without loading raw page files.
- `scripts/ui_app/config_summary.py`: reads project source, competitor, target-brand, and model options for the local UI.
- `scripts/ui_app/report_summary.py`: finds the latest merged run report and summarizes target ranking, top competitors, and model-level slices.
- `scripts/ui_app/run_plan.py`: builds explicit dry-run command plans for owned-site refresh, corpus rebuild, optional cloud sync, and API benchmark execution.
- `scripts/ui_app/server.py`: serves the local browser console with standard-library HTTP only; it reads status and returns dry-run plans but does not execute API or AWS calls.
- `sql/001_initial_schema.sql`: defines the cloud resource-library schema, including corpus versions, artifact objects, documents, chunks, query sets, benchmark runs, and result tables.

## Data Flow

1. Source config / TSV input
2. URL discovery
3. New URL filtering
4. Tiered crawl
5. Raw page merge
6. Document cleaning
7. Chunking
8. Page signals and evidence cards
9. BM25 and Qdrant indexing
10. Retrieval / rerank / answer evaluation
11. Brand and gap reports
12. Optional corpus-variant comparison for with/without `llms.txt` experiments
13. Optional cloud import of clean inventory/documents/chunks into PostgreSQL, with source snapshots registered in S3 as artifacts
14. Optional local UI review of corpus status, configured models, competitors, latest reports, and dry-run command plans

## Cloud Store

- Current AWS region: `ap-northeast-1`.
- Current S3 bucket: `geo-resource-library-prod-940329548423-ap-northeast-1-an`.
- Current RDS identifier: `geo-postgres-prod`.
- Current RDS endpoint: `geo-postgres-prod.cbkgwuwamngl.ap-northeast-1.rds.amazonaws.com`.
- Current imported corpus version: `2026-05-22-initial`.
- Current default industry: `geo-agency`.

The cloud store follows the project split documented in `docs/cloud-database.md`: PostgreSQL is the queryable corpus and benchmark ledger, S3 is the artifact store, and Qdrant is rebuildable from versioned chunks. Cloud rows are isolated by `industry_id` first, then by `corpus_version` or `query_set_version`.

## Dependency Direction

- Crawlers produce raw data and must not depend on evaluator logic.
- Cleaning and chunking depend on raw data and inventory metadata only.
- Retrieval and evaluation depend on processed documents, chunks, indexes, and evidence cards.
- Report generation depends on evaluation outputs and corpus stats.
- Full external API execution must be explicit and user-run.
- Incremental output writing belongs inside the simulator orchestration layer; monitor scripts read those files and must not mutate run state.
- Resume behavior uses persisted output files as the contract: scenario rows, rerank rows, and answer rows determine what is already complete.
- Seeded parallel runs reuse `api_queries.csv` per model so scenario generation remains fixed while retrieval, rerank, and answer evaluation use the refreshed corpus; the seeded row count must be capped to the effective `queries_per_model`.
- Corpus variants must write to separate directories such as `data/experiments/without_llms/processed` and separate config files so control experiments cannot overwrite the main resource library.
- Run-mode selection belongs in the PowerShell orchestration layer: `quick` maps to 50 queries per model, while `standard` maps to 200 queries per model unless `-QueriesPerModel` explicitly overrides it.
- Cloud import depends on existing processed contracts; it must not become a hidden crawler or evaluator path.
- PostgreSQL is the queryable corpus and benchmark ledger, S3 is the artifact store, and Qdrant remains a rebuildable retrieval index.
- Industry isolation belongs in the cloud operation layer: cloud imports, verification, S3 artifact keys, and Qdrant snapshots must require an explicit `industry_id`.
- The local UI depends on existing configs, processed artifacts, reports, and cloud environment presence only; it must call orchestration scripts explicitly rather than reimplementing crawler, evaluator, or cloud import logic.

## Boundaries

- Do not mix crawler fetch logic with evaluation logic.
- Do not mix report aggregation with API call orchestration unless the data contract is explicit.
- Do not add broad "manager" or "service" modules that hide unrelated responsibilities.
- Do not bypass existing cache/run-state abstractions without documenting why.
- Do not let one-off scripts become the main path without either tests or a documented migration note.
- Do not compare `llms.txt` effects by changing scenario questions at the same time; A/B runs must use the same seeded query set and differ only in corpus inputs.
- Do not treat S3 as a query database; store object keys and hashes in PostgreSQL and keep large snapshots in S3.
- Do not treat Qdrant as the source of truth; it must be rebuildable from versioned chunks.
- Cloud verification commands must remain read-only unless the user explicitly starts an import or snapshot command.
- Do not run a cloud command without `--industry`; adding a new industry should create a new `industry_id`, not reuse `geo-agency`.
- Do not let the UI become a hidden execution layer for paid crawlers, model APIs, or AWS writes; execution buttons need explicit command previews, logs, and guardrails.
