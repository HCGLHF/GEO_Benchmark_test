# Architecture

## Modules

- `scripts/discover_site_urls.py`: discovers same-site URLs from seeds, sitemaps, robots, and links.
- `scripts/crawl_pages.py` and `scripts/crawl_pages_parallel.py`: tiered page fetchers using `httpx`, Playwright, and optional paid fallback.
- `scripts/clean_documents.py`: converts raw pages into document records with brand metadata.
- `scripts/chunk_documents.py`: splits documents into retrieval chunks.
- `scripts/build_keyword_index.py`: builds the local BM25-style keyword artifact.
- `scripts/build_vector_index.py`: builds the local Qdrant vector index.
- `scripts/client_acquisition_simulator.py`: orchestrates scenario generation, retrieval, rerank, answers, brand metrics, competitive reports, and incremental run-output writes.
- `scripts/run_full_api_client_acquisition.py`: user-run entrypoint for highest-fidelity external API evaluation.
- `scripts/run_full_api_parallel_with_watch.ps1`: one-command local orchestrator that launches one full API worker per model, monitors each run, and merges successful outputs.
- `scripts/watch_full_api_run.py`: read-only monitor for long full API runs, summarizing progress from run output files without calling model APIs.
- `scripts/merge_full_api_runs.py`: merges single-model runs into one report.

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

## Dependency Direction

- Crawlers produce raw data and must not depend on evaluator logic.
- Cleaning and chunking depend on raw data and inventory metadata only.
- Retrieval and evaluation depend on processed documents, chunks, indexes, and evidence cards.
- Report generation depends on evaluation outputs and corpus stats.
- Full external API execution must be explicit and user-run.
- Incremental output writing belongs inside the simulator orchestration layer; monitor scripts read those files and must not mutate run state.

## Boundaries

- Do not mix crawler fetch logic with evaluation logic.
- Do not mix report aggregation with API call orchestration unless the data contract is explicit.
- Do not add broad "manager" or "service" modules that hide unrelated responsibilities.
- Do not bypass existing cache/run-state abstractions without documenting why.
- Do not let one-off scripts become the main path without either tests or a documented migration note.
