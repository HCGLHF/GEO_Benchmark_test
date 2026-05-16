# GEO Benchmark Sandbox Design

## Purpose

Build a private GEO benchmark system that measures whether owned content can be retrieved, cited, and used by LLM-style answer systems when compared with competitor and industry content.

The system should not claim to reproduce any public model's private retrieval pipeline. It should create a controlled, repeatable sandbox that can answer:

- Does our content enter the top retrieval results for target queries?
- Do model answers mention our brand?
- Do model answers cite our URLs?
- Do competitors outrank or displace our content?
- Does our content cover the user's real intent?
- Do content updates improve those metrics over time?

## Core Design Choice

The benchmark is split into two layers.

### Layer A: Controlled Retrieval Sandbox

This layer owns the corpus and retrieval pipeline. It is the only layer that can produce true retrieval metrics such as `Recall@5`.

Inputs:

- Owned website pages.
- Competitor pages.
- Industry authority pages.
- Query library.

Processing:

- Crawl pages.
- Extract readable content.
- Normalize page metadata.
- Chunk documents.
- Embed chunks.
- Store vectors and metadata.
- Run top-k retrieval for each query.

Outputs:

- Retrieved chunks and URLs.
- Owned brand rank.
- Competitor rank.
- `Recall@3`, `Recall@5`, and `Recall@10`.
- Competitor win rate.

### Layer B: Model Answer Arena

This layer evaluates model answers from external APIs and local models. It does not provide true internal model retrieval visibility unless the model API exposes citations or search results.

Inputs:

- Same query library as Layer A.
- Optional retrieved context from Layer A.
- Provider and model configuration.

Modes:

- `direct`: ask the model without supplied context.
- `grounded`: give the model the same top-k retrieved chunks from Layer A.

Outputs:

- Raw answer.
- Extracted citations.
- Mentioned brands.
- Recommendation flags.
- Coverage score.
- Hallucination or unsupported claim flags.

## Recommended MVP Architecture

Use Python scripts with explicit files and tables rather than a full RAG framework.

Primary components:

- `trafilatura` or Playwright for crawling and content extraction.
- `BGE-M3` for local multilingual embeddings.
- `Qdrant` for vector search.
- `rank-bm25` or SQLite FTS5 for keyword retrieval.
- Reciprocal Rank Fusion for hybrid retrieval.
- SQLite or DuckDB for experiment records.
- CSV and Markdown report outputs.

The MVP should keep the pipeline transparent. LlamaIndex, LangChain, Ragas, DeepEval, or Phoenix can be added later where they help, but they should not hide the business metric logic.

## Data Flow

```text
config/sources.yaml
data/eval/queries.csv
        |
        v
scripts/crawl_pages.py
        |
        v
data/raw/pages.jsonl
        |
        v
scripts/clean_documents.py
        |
        v
data/processed/documents.jsonl
        |
        v
scripts/chunk_documents.py
        |
        v
data/processed/chunks.jsonl
        |
        +--> scripts/build_vector_index.py --> Qdrant
        |
        +--> scripts/build_keyword_index.py --> SQLite FTS5 or BM25 artifacts
        |
        v
scripts/eval_retrieval.py
        |
        v
scripts/eval_generation.py
        |
        v
scripts/generate_report.py
```

## Experiment Database

Use `data/geo_benchmark.sqlite` or `data/geo_benchmark.duckdb`.

### `runs`

Records each evaluation run.

Columns:

- `run_id`
- `created_at`
- `run_type`: `retrieval`, `generation`, or `full`
- `corpus_version`
- `query_set_version`
- `retriever_type`: `vector`, `keyword`, or `hybrid`
- `embedding_model`
- `chunk_strategy`
- `top_k`
- `notes`

### `queries`

Stores query metadata.

Columns:

- `query_id`
- `query`
- `intent`
- `priority`
- `target_brand`
- `expected_owned_urls`
- `notes`

### `documents`

Stores cleaned document metadata.

Columns:

- `document_id`
- `url`
- `site`
- `brand`
- `source_type`
- `page_type`
- `title`
- `description`
- `collected_at`
- `content_hash`

### `chunks`

Stores chunk metadata and references.

Columns:

- `chunk_id`
- `document_id`
- `url`
- `brand`
- `source_type`
- `page_type`
- `heading`
- `text`
- `token_count`
- `content_hash`

### `retrieval_results`

Stores one row per query per run.

Columns:

- `run_id`
- `query_id`
- `top_k`
- `own_brand_rank`
- `own_brand_in_top_3`
- `own_brand_in_top_5`
- `own_brand_in_top_10`
- `winning_brand`
- `winning_source_type`
- `competitor_above_owned`
- `matched_urls_json`
- `retrieved_chunks_json`

### `generation_results`

Stores one row per query, model, mode, and repeat.

Columns:

- `run_id`
- `query_id`
- `provider`
- `model_name`
- `mode`: `direct` or `grounded`
- `repeat_index`
- `temperature`
- `prompt_version`
- `context_top_k`
- `raw_answer`
- `brand_mentioned`
- `cited_own_url`
- `recommended_own_brand`
- `competitors_mentioned_json`
- `citations_json`
- `answer_coverage_score`
- `unsupported_claims_json`
- `latency_ms`
- `cost_estimate`

## Metric Definitions

### Recall@5

True only for the controlled retrieval sandbox.

Definition:

`owned content is present in the top 5 retrieved chunks for a query`.

Reported as:

```text
queries_with_owned_content_in_top_5 / total_queries
```

### Brand Mention Rate

Definition:

`model answer mentions the target owned brand by exact name or accepted alias`.

Reported as:

```text
answers_mentioning_owned_brand / total_answers
```

### Citation Rate

Definition:

`model answer cites at least one owned URL`.

For direct mode, citations depend on the model output. For grounded mode, citations should be enforced by prompt format and validated against retrieved context URLs.

### Competitor Win Rate

Retrieval definition:

`a competitor chunk ranks above the first owned chunk, or no owned chunk appears while competitor content appears`.

Generation definition:

`the answer recommends or prominently cites a competitor without comparable owned brand mention or citation`.

These two should be reported separately.

### Answer Coverage

Definition:

`the answer addresses the user's actual intent using supported information`.

MVP scoring:

- `0`: does not answer the intent.
- `1`: partially answers, misses key decision factors.
- `2`: answers the main intent but lacks proof, caveats, or specificity.
- `3`: fully answers with relevant factors, evidence, and grounded claims.

The first version can combine simple rule checks with an LLM judge. Human spot checks should be used to calibrate the judge.

## Repetition Strategy

Do not start with 1000 repeats per query.

Recommended MVP:

- 100 to 200 queries.
- 3 to 5 model providers or models.
- 3 repeats per query for direct mode.
- 1 repeat per query for grounded mode when temperature is 0.
- Increase repeats only for stability testing after the pipeline works.

Use deterministic settings where possible:

- `temperature = 0` for grounded evaluation.
- Higher temperature only for variability experiments.

## Prompting Requirements

Generation prompts should be versioned.

Grounded mode should require:

- Answer only from supplied context.
- Cite URLs inline or in a structured citations field.
- Say when context is insufficient.
- Avoid unsupported claims.

Direct mode should avoid mentioning the benchmark setup and should simulate a normal user query.

## Error Handling

The pipeline should never stop an entire run because one URL, query, or API call fails.

Required behavior:

- Failed crawls are logged with URL, status, and error message.
- API errors are retried with backoff.
- Failed generation rows are recorded with an error field.
- Missing citations are treated as metric failures, not script failures.
- Every run has enough metadata to be reproduced.

## MVP Scope

Included:

- Local corpus ingestion.
- Qdrant vector index.
- Keyword retrieval index.
- Hybrid retrieval using RRF.
- Retrieval metrics.
- Model answer collection for API providers.
- Rule-based brand and citation extraction.
- Basic answer coverage scoring.
- SQLite or DuckDB run storage.
- CSV and Markdown report.

Deferred:

- Full web dashboard.
- Complex agent workflows.
- Automated content rewriting.
- Public search engine scraping.
- Claims that external model APIs reveal their hidden retrieval set.
- Large-scale 1000-repeat testing before the MVP is stable.

## Acceptance Criteria

The first version is successful when it can:

- Crawl and clean at least 100 pages.
- Build vector and keyword indexes from chunks.
- Run at least 100 queries through retrieval evaluation.
- Produce `Recall@5`, competitor win rate, and owned brand rank.
- Run at least two model providers in direct and grounded modes.
- Produce brand mention rate, citation rate, competitor mention rate, and answer coverage.
- Save all raw answers and run metadata for later comparison.
- Generate a Markdown report that identifies weak queries and pages to optimize first.

