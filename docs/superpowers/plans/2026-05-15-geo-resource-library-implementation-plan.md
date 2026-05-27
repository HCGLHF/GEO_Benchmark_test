# GEO Resource Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working GEO resource library MVP: tiered crawling, content cleaning, chunking, Qdrant indexing, SQLite run storage, retrieval evaluation, generation evaluation, and Markdown reporting.

**Architecture:** The system is a Python script pipeline with explicit JSONL/CSV files as durable handoff points. Shared code lives in `scripts/_common.py`, while user-facing commands remain in `scripts/*.py` to match `geo-resource-library-plan.md`.

**Tech Stack:** Python 3.11+, `httpx`, `trafilatura`, `playwright`, `pyyaml`, `pydantic`, `pandas`, `qdrant-client`, `FlagEmbedding`, `rank-bm25`, `openai`, `pytest`.

---

## Implementation Defaults

- Current workspace is not a git repository, so this plan omits commit steps. If a git repository is initialized before implementation, commit after each completed task with a focused message.
- Use `Qdrant` as the primary vector database. Keep `Chroma` out of v1 implementation.
- Use `SQLite` for experiment/run storage.
- Paid crawler providers are configurable adapters in v1, but MVP must run without paid API keys.
- Generation evaluation supports OpenAI-compatible APIs first. DeepSeek and Qwen can use the same interface when configured with their base URLs.
- No public search engine scraping in v1.

## File Structure To Create

```text
config/
  sources.yaml
  crawler.yaml
  eval.yaml
data/
  raw/
    pages.jsonl
    fetch_attempts.jsonl
    crawl_logs.csv
  processed/
    documents.jsonl
    chunks.jsonl
  eval/
    queries.csv
    retrieval_results.csv
    generation_results.csv
  geo_benchmark.sqlite
reports/
  geo_report.md
scripts/
  __init__.py
  _common.py
  collect_urls.py
  crawl_pages.py
  score_content_quality.py
  paid_fetch_fallback.py
  clean_documents.py
  chunk_documents.py
  build_vector_index.py
  build_keyword_index.py
  eval_retrieval.py
  eval_generation.py
  generate_report.py
tests/
  test_common.py
  test_score_content_quality.py
  test_collect_urls.py
  test_chunk_documents.py
  test_eval_retrieval.py
pyproject.toml
README.md
```

## Task 1: Project Scaffold And Dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: directory tree listed above
- Create: `scripts/__init__.py`

- [ ] **Step 1: Create package metadata and dependencies**

Create `pyproject.toml` with these exact dependency groups:

```toml
[project]
name = "geo-resource-library"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "httpx>=0.27",
  "trafilatura>=1.9",
  "playwright>=1.45",
  "pyyaml>=6.0",
  "pydantic>=2.7",
  "pandas>=2.2",
  "qdrant-client>=1.9",
  "FlagEmbedding>=1.2",
  "rank-bm25>=0.2.2",
  "openai>=1.40",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: Create the README**

Create `README.md` with:

```markdown
# GEO Resource Library

This project builds a private retrieval and generation benchmark for GEO optimization. It crawls owned, competitor, and industry pages, then evaluates whether owned content is retrieved, mentioned, cited, and recommended by LLM-style answer systems.

## MVP Pipeline

1. Configure sources and queries.
2. Crawl pages with tiered fetch methods.
3. Clean pages into documents.
4. Chunk documents.
5. Build vector and keyword indexes.
6. Run retrieval evaluation.
7. Run generation evaluation.
8. Generate a Markdown report.
```

- [ ] **Step 3: Verify scaffold imports**

Run:

```powershell
python -m pytest -q
```

Expected: pytest starts and reports either no tests collected or all current tests pass.

## Task 2: Shared Schemas, JSONL Utilities, And SQLite Setup

**Files:**
- Create: `scripts/_common.py`
- Test: `tests/test_common.py`

- [ ] **Step 1: Write tests for shared records and JSONL round trip**

Create `tests/test_common.py` with tests that assert:

- `RawPageRecord` accepts all required fields from `geo-resource-library-plan.md`.
- `write_jsonl()` writes one JSON object per line.
- `read_jsonl()` returns the original objects.
- `init_sqlite()` creates `runs`, `documents`, `chunks`, `retrieval_results`, and `generation_results`.

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```powershell
python -m pytest tests/test_common.py -q
```

Expected: failure caused by missing `scripts._common`.

- [ ] **Step 3: Implement shared code**

Create `scripts/_common.py` with:

- Pydantic models: `RawPageRecord`, `FetchAttemptRecord`, `DocumentRecord`, `ChunkRecord`, `QueryRecord`, `RetrievalResultRecord`, `GenerationResultRecord`.
- Enum-like constants:
  - `FETCH_METHODS = {"httpx", "playwright", "firecrawl", "scrapingbee", "zyte", "bright_data", "apify", "browserless"}`
  - `ERROR_TYPES = {"blocked", "captcha", "timeout", "http_error", "empty_content", "low_quality_content", "parse_error", "unknown"}`
- Functions:
  - `utc_now_iso() -> str`
  - `stable_id(prefix: str, value: str) -> str`
  - `read_jsonl(path: Path) -> list[dict]`
  - `append_jsonl(path: Path, records: Iterable[BaseModel | dict]) -> None`
  - `write_jsonl(path: Path, records: Iterable[BaseModel | dict]) -> None`
  - `content_hash(text: str) -> str`
  - `init_sqlite(path: Path) -> None`

SQLite tables must include the columns listed in `docs/superpowers/specs/2026-05-15-geo-benchmark-design.md`.

- [ ] **Step 4: Run shared-code tests**

Run:

```powershell
python -m pytest tests/test_common.py -q
```

Expected: all tests in `test_common.py` pass.

## Task 3: Configuration Files And URL Collection

**Files:**
- Create: `config/sources.yaml`
- Create: `config/crawler.yaml`
- Create: `config/eval.yaml`
- Create: `scripts/collect_urls.py`
- Test: `tests/test_collect_urls.py`

- [ ] **Step 1: Write config fixtures and tests**

Create `tests/test_collect_urls.py` with tests for:

- Owned-site URLs, competitor URLs, and industry-source URLs are normalized into a flat list.
- Duplicate URLs are removed.
- Each output row preserves `brand` and `source_type`.

- [ ] **Step 2: Create starter configs**

Create `config/sources.yaml` with reserved example domains only:

```yaml
own_site:
  brand: "Your Brand"
  source_type: "official_site"
  urls:
    - "https://example.com/"
    - "https://example.com/product"

competitors:
  - brand: "Competitor A"
    source_type: "competitor_site"
    urls:
      - "https://competitor-a.example/"

industry_sources:
  - brand: "Industry Media"
    source_type: "review_site"
    urls:
      - "https://industry.example/best-tools"
```

Create `config/crawler.yaml`:

```yaml
quality_thresholds:
  good: 0.7
  partial: 0.4

timeouts:
  httpx_seconds: 20
  playwright_seconds: 45

paid_fallback:
  enabled: false
  default_provider: "firecrawl"
```

Create `config/eval.yaml`:

```yaml
top_k: 10
retriever_type: "hybrid"
embedding_model: "BAAI/bge-m3"
generation:
  mode: "grounded"
  temperature: 0
```

- [ ] **Step 3: Implement `collect_urls.py`**

The script must:

- Read `config/sources.yaml`.
- Produce rows with `url`, `brand`, `source_type`, and `source_group`.
- Print the normalized URL count.
- Write `data/raw/url_inventory.csv`.

- [ ] **Step 4: Verify URL collection**

Run:

```powershell
python -m pytest tests/test_collect_urls.py -q
python scripts/collect_urls.py --config config/sources.yaml --output data/raw/url_inventory.csv
```

Expected: tests pass and `data/raw/url_inventory.csv` contains the starter URLs.

## Task 4: Content Quality Scoring

**Files:**
- Create: `scripts/score_content_quality.py`
- Test: `tests/test_score_content_quality.py`

- [ ] **Step 1: Write quality scoring tests**

Create tests for:

- Empty extracted text scores below `0.4` and returns `empty_content`.
- Captcha or blocked text scores below `0.4` and returns `blocked` or `captcha`.
- Normal article-like text with a title scores at least `0.7`.
- Missing title reduces score.
- Very low text-to-HTML ratio reduces score.

- [ ] **Step 2: Implement scoring**

Create `score_content_quality.py` with:

- `score_content(title: str | None, html: str, text: str, status_code: int | None) -> tuple[float, str | None]`
- Blocking keyword detection for `captcha`, `access denied`, `cloudflare`, `verify you are human`, and `too many requests`.
- Score calculation:
  - Start from `1.0`.
  - Set to `0.0` for empty text.
  - Cap at `0.3` for captcha or blocked access.
  - Subtract `0.2` for missing title.
  - Subtract `0.2` when text length is under 500 characters.
  - Subtract `0.2` when text-to-HTML ratio is below `0.03`.
  - Clamp to `0.0` through `1.0`.

- [ ] **Step 3: Verify quality scoring**

Run:

```powershell
python -m pytest tests/test_score_content_quality.py -q
```

Expected: all quality scoring tests pass.

## Task 5: Tiered Crawler And Paid Fallback Adapter

**Files:**
- Create: `scripts/crawl_pages.py`
- Create: `scripts/paid_fetch_fallback.py`
- Test: extend `tests/test_score_content_quality.py` or create focused crawler tests if network-free mocks are needed

- [ ] **Step 1: Implement paid provider adapter boundaries**

Create `paid_fetch_fallback.py` with:

- `PaidFetchResult` model: `provider`, `status_code`, `html`, `markdown`, `error_type`, `error_message`.
- `fetch_with_paid_provider(url: str, provider: str, config: dict) -> PaidFetchResult`.
- Provider keys supported in config: `firecrawl`, `scrapingbee`, `zyte`, `bright_data`, `apify`, `browserless`.
- When `paid_fallback.enabled` is false, return an error result with `error_type="unknown"` and `error_message="paid fallback disabled"`.

- [ ] **Step 2: Implement `crawl_pages.py`**

The script must:

- Read `data/raw/url_inventory.csv`.
- Try Level 1 with `httpx`.
- Extract markdown/text with `trafilatura`.
- Score content with `score_content()`.
- Try Level 2 with Playwright when score is below `0.4` or `error_type` is blocking-related.
- Try Level 3 paid fallback only when `paid_fallback.enabled` is true.
- Write successful raw pages to `data/raw/pages.jsonl`.
- Write every attempt to `data/raw/fetch_attempts.jsonl`.
- Write a summary CSV to `data/raw/crawl_logs.csv`.

- [ ] **Step 3: Verify crawler help and dry behavior**

Run:

```powershell
python scripts/crawl_pages.py --help
```

Expected: command prints usage, including `--url-inventory`, `--crawler-config`, `--pages-output`, and `--attempts-output`.

## Task 6: Clean Documents And Chunk Content

**Files:**
- Create: `scripts/clean_documents.py`
- Create: `scripts/chunk_documents.py`
- Test: `tests/test_chunk_documents.py`

- [ ] **Step 1: Write chunking tests**

Create tests for:

- Chinese text chunks stay between 300 and 800 Chinese characters when possible.
- English text chunks stay between 200 and 500 words when possible.
- FAQ question-answer pairs stay in the same chunk.
- Each chunk has `chunk_id`, `document_id`, `url`, `brand`, `title`, `text`, `source_type`, `page_type`, and `token_count`.

- [ ] **Step 2: Implement `clean_documents.py`**

The script must:

- Read `data/raw/pages.jsonl`.
- Convert raw pages into `DocumentRecord`.
- Use URL hostname as `site`.
- Carry through `brand` and `source_type` by joining with `data/raw/url_inventory.csv`.
- Write `data/processed/documents.jsonl`.

- [ ] **Step 3: Implement `chunk_documents.py`**

The script must:

- Read `data/processed/documents.jsonl`.
- Split Chinese and English using the documented size rules.
- Keep detected FAQ pairs together when a line ending with `?` or `？` is followed by answer text.
- Write `data/processed/chunks.jsonl`.

- [ ] **Step 4: Verify cleaning and chunking**

Run:

```powershell
python -m pytest tests/test_chunk_documents.py -q
```

Expected: chunking tests pass.

## Task 7: SQLite Run Storage, Vector Index, And Keyword Index

**Files:**
- Create: `scripts/build_vector_index.py`
- Create: `scripts/build_keyword_index.py`
- Modify: `scripts/_common.py` if table setup needs additional indexes

- [ ] **Step 1: Implement SQLite initialization**

Ensure `init_sqlite(data/geo_benchmark.sqlite)` creates all experiment tables before indexing or evaluation scripts run.

- [ ] **Step 2: Implement Qdrant vector indexing**

`build_vector_index.py` must:

- Read `data/processed/chunks.jsonl`.
- Embed `text` using `BAAI/bge-m3` through `FlagEmbedding`.
- Create or recreate Qdrant collection `geo_chunks`.
- Upsert each chunk with metadata payload: `chunk_id`, `document_id`, `url`, `brand`, `title`, `source_type`, `page_type`, `heading`, and `token_count`.
- Store local Qdrant data under `vector_db/qdrant/` when using embedded/local mode.

- [ ] **Step 3: Implement keyword index**

`build_keyword_index.py` must:

- Read `data/processed/chunks.jsonl`.
- Tokenize text with simple whitespace and character fallback for Chinese.
- Build a `rank-bm25` index.
- Save a pickle artifact to `data/processed/bm25_index.pkl`.

- [ ] **Step 4: Verify index scripts expose help**

Run:

```powershell
python scripts/build_vector_index.py --help
python scripts/build_keyword_index.py --help
```

Expected: both commands print usage and include input/output arguments.

## Task 8: Retrieval Evaluation

**Files:**
- Create: `scripts/eval_retrieval.py`
- Test: `tests/test_eval_retrieval.py`

- [ ] **Step 1: Write metric tests**

Create tests for:

- `own_brand_rank` is `1` when owned content is first.
- `own_brand_in_top_5` is true when owned content appears at rank 5.
- `competitor_above_owned` is true when a competitor appears before the first owned result.
- `winning_brand` is the brand at rank 1.

- [ ] **Step 2: Implement retrieval evaluation**

`eval_retrieval.py` must:

- Read `data/eval/queries.csv`.
- Run vector retrieval from Qdrant.
- Run keyword retrieval from the BM25 artifact.
- Combine results with reciprocal rank fusion.
- Produce one result row per query.
- Write `data/eval/retrieval_results.csv`.
- Insert rows into SQLite `retrieval_results`.

- [ ] **Step 3: Verify retrieval metrics**

Run:

```powershell
python -m pytest tests/test_eval_retrieval.py -q
```

Expected: retrieval metric tests pass.

## Task 9: Generation Evaluation

**Files:**
- Create: `scripts/eval_generation.py`

- [ ] **Step 1: Implement provider config**

`eval_generation.py` must read provider settings from environment variables:

- `GEO_LLM_PROVIDER`
- `GEO_LLM_MODEL`
- `GEO_LLM_BASE_URL`
- `GEO_LLM_API_KEY`

When `GEO_LLM_API_KEY` is missing, the script must exit with a clear message and must not create a partial `generation_results.csv`.

- [ ] **Step 2: Implement grounded prompt mode**

Grounded mode prompt must require:

- Answer only from supplied context.
- Cite URLs from supplied chunks.
- Say when context is insufficient.
- Avoid unsupported claims.

- [ ] **Step 3: Implement answer scoring**

Compute:

- `brand_mentioned` by exact brand or accepted alias match.
- `cited_own_url` by URL match against owned URLs.
- `recommended_own_brand` by brand mention near recommendation terms.
- `competitors_mentioned_json` by matching competitor brands.
- `answer_coverage_score` from `0` to `3` using the rubric in the design doc.

- [ ] **Step 4: Verify no-key behavior**

Run:

```powershell
python scripts/eval_generation.py --queries data/eval/queries.csv --retrieval-results data/eval/retrieval_results.csv
```

Expected: command exits with a clear missing-key message and does not create partial generation output.

## Task 10: Report Generation

**Files:**
- Create: `scripts/generate_report.py`
- Create: `reports/geo_report.md`

- [ ] **Step 1: Implement report generation**

`generate_report.py` must:

- Read `data/eval/retrieval_results.csv`.
- Read `data/eval/generation_results.csv` when present.
- Calculate Recall@3, Recall@5, Recall@10, Brand Mention Rate, Citation Rate, Recommendation Rate, Competitor Win Rate, and Coverage Score.
- List the weakest queries where owned content did not appear in Top 10.
- List pages that should be optimized first based on low retrieval rank or missing citation.
- Write `reports/geo_report.md`.

- [ ] **Step 2: Verify report command**

Run:

```powershell
python scripts/generate_report.py --retrieval-results data/eval/retrieval_results.csv --generation-results data/eval/generation_results.csv --output reports/geo_report.md
```

Expected: if generation results are absent, the report still renders retrieval sections and states that generation evaluation has not been run.

## Task 11: End-To-End Smoke Run

**Files:**
- Use all created pipeline files

- [ ] **Step 1: Create minimal sample input**

Create one owned URL row and one query row using local/example data:

- `data/raw/url_inventory.csv`
- `data/eval/queries.csv`

Use `example.com` style domains only unless real targets are provided.

- [ ] **Step 2: Run non-network tests**

Run:

```powershell
python -m pytest -q
```

Expected: all unit tests pass.

- [ ] **Step 3: Run help checks for every script**

Run:

```powershell
python scripts/collect_urls.py --help
python scripts/crawl_pages.py --help
python scripts/clean_documents.py --help
python scripts/chunk_documents.py --help
python scripts/build_vector_index.py --help
python scripts/build_keyword_index.py --help
python scripts/eval_retrieval.py --help
python scripts/eval_generation.py --help
python scripts/generate_report.py --help
```

Expected: each script prints usage and exits successfully.

## Self-Review Checklist

- Every requirement in `geo-resource-library-plan.md` sections 4, 5, 6, 7, 10, 11, and 14 maps to at least one task above.
- The plan uses Qdrant as the primary vector database.
- The plan keeps paid crawler services as fallback adapters.
- The plan includes quality scoring before crawl-level escalation.
- The plan includes SQLite run storage.
- The plan includes retrieval and generation evaluation.
- The plan includes report generation.
- The plan avoids public search engine scraping.
