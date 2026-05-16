# GEO Resource Library Implementation Plan

## 1. Goal

Build a private GEO testing resource library that simulates how an LLM with retrieval might discover, rank, and cite website content.

The system is not meant to prove that public LLMs have already crawled the website. It is meant to answer this question:

> If an LLM can see our website and competing sources, will it retrieve, trust, and use our content in answers?

## 2. What This System Tests

The resource library should measure:

- Whether our pages are retrieved for target non-brand queries.
- Whether our chunks appear in Top 3, Top 5, or Top 10 results.
- Whether generated answers mention our brand.
- Whether generated answers cite our pages.
- Whether competitor content wins over our content.
- Whether page updates improve retrieval and citation performance.

## 3. MVP Scope

Start with a small but realistic corpus:

| Source Type | Suggested Count | Purpose |
|---|---:|---|
| Our website pages | 20-50 | Test our content visibility |
| Competitor pages | 50-150 | Simulate competition |
| Industry authority pages | 30-100 | Simulate external knowledge sources |
| Test queries | 50-200 | Evaluate common user intents |

Recommended MVP:

- 100 total web pages
- 100 test queries
- 1 embedding model
- 1 vector database
- 1 retrieval evaluation script
- 1 generation evaluation script
- 1 Markdown or CSV report output

## 4. Recommended Stack

For a fast local MVP:

```text
Default crawler: httpx + trafilatura
JS fallback crawler: Playwright
Paid fallback crawler: Firecrawl, ScrapingBee, Zyte, Bright Data, or Apify
Content extraction: trafilatura
Embedding model: bge-m3
Vector database: Qdrant
Optional demo vector database: Chroma
Experiment storage: SQLite or DuckDB
LLM: Qwen, DeepSeek, Llama, or OpenAI API
Framework: plain Python scripts first; LlamaIndex or LangChain only if useful later
Storage format: JSONL + CSV + SQLite/DuckDB
```

For a more production-like setup:

```text
Default crawler: httpx + trafilatura
JS fallback crawler: Playwright
Paid fallback crawler: Firecrawl, ScrapingBee, Zyte, Bright Data, or Apify
Content extraction: trafilatura
Embedding model: bge-m3 or jina-embeddings-v3
Vector database: Qdrant
Experiment storage: SQLite or DuckDB
LLM: OpenAI API, DeepSeek API, Qwen API, or local model
Framework: plain Python scripts with optional LlamaIndex integration
Evaluation output: CSV + Markdown report
```

## 5. Project Structure

Suggested folder layout:

```text
geo-resource-library/
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
  vector_db/
    qdrant/
  reports/
    geo_report.md
  scripts/
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
  config/
    sources.yaml
    crawler.yaml
    eval.yaml
  README.md
```

## 6. Data Model

### 6.1 URL Source Config

Use `config/sources.yaml` to define source groups:

```yaml
own_site:
  brand: "Your Brand"
  source_type: "official_site"
  urls:
    - "https://example.com/"
    - "https://example.com/product"
    - "https://example.com/pricing"

competitors:
  - brand: "Competitor A"
    source_type: "competitor_site"
    urls:
      - "https://competitor-a.com/"
      - "https://competitor-a.com/product"

industry_sources:
  - brand: "Industry Media"
    source_type: "review_site"
    urls:
      - "https://industry-site.com/best-tools"
```

### 6.2 Raw Page Record

Each fetch attempt should preserve the raw retrieval result in `data/raw/pages.jsonl` when it succeeds, and each attempted method should be logged in `data/raw/fetch_attempts.jsonl`.

```json
{
  "url": "https://example.com/product",
  "final_url": "https://example.com/product",
  "status_code": 200,
  "fetch_method": "httpx",
  "html": "<html>...</html>",
  "markdown": "# Product Page Title\n\nClean extracted page content...",
  "content_quality_score": 0.86,
  "error_type": null,
  "error_message": null,
  "collected_at": "2026-05-15"
}
```

Allowed `fetch_method` values:

```text
httpx
playwright
firecrawl
scrapingbee
zyte
bright_data
apify
browserless
```

Recommended `error_type` values:

```text
blocked
captcha
timeout
http_error
empty_content
low_quality_content
parse_error
unknown
```

### 6.3 Document Record

Each cleaned page should be stored in `data/processed/documents.jsonl`:

```json
{
  "document_id": "doc_001",
  "url": "https://example.com/product",
  "site": "example.com",
  "brand": "Your Brand",
  "title": "Product Page Title",
  "description": "Page meta description",
  "content": "Cleaned main page content...",
  "source_type": "official_site",
  "page_type": "product_page",
  "collected_at": "2026-05-15"
}
```

### 6.4 Chunk Record

Each chunk should be stored in `data/processed/chunks.jsonl`:

```json
{
  "chunk_id": "chunk_001",
  "document_id": "doc_001",
  "url": "https://example.com/product",
  "brand": "Your Brand",
  "title": "Product Page Title",
  "heading": "Who is this product for?",
  "text": "This product is suitable for...",
  "source_type": "official_site",
  "page_type": "product_page",
  "token_count": 420
}
```

## 7. Crawling Architecture

Use a tiered crawling system. The crawler should start with the cheapest reliable method, measure content quality, and upgrade only when the result is blocked, empty, or too low quality.

### 7.1 URL Collection

Collect URLs from:

- `config/sources.yaml`
- XML sitemaps
- Manually curated competitor and industry URL lists
- Product, pricing, FAQ, comparison, blog, documentation, and case study pages

The crawler should not treat this as a general-purpose search engine. The resource library is a controlled GEO/RAG benchmark corpus, so source selection should stay curated and explainable.

### 7.2 Level 1: HTTP Fetch

Default method:

```text
httpx + trafilatura
```

Use this for:

- Own website pages
- Ordinary competitor website pages
- Blog posts
- Documentation pages
- Static pricing or product pages
- Industry articles and review pages

Level 1 should be the default because it is fast, cheap, easy to debug, and good enough for most pages.

### 7.3 Level 2: Browser Rendering

Fallback method:

```text
Playwright
```

Use this when Level 1 returns low-quality content or cannot see content rendered by JavaScript.

Typical cases:

- SPA pages
- React, Vue, or Next.js pages that hydrate content client-side
- Lazy-loaded pricing tables
- Folded FAQ blocks
- Product pages that require scrolling before content appears

The Playwright crawler should wait for the main content area, scroll when needed, and then save rendered HTML for extraction.

### 7.4 Level 3: Paid Crawler API

Paid fallback should be used only for URLs that fail the free and self-hosted tiers.

Use Level 3 for:

- `403` responses
- Cloudflare or similar anti-bot blocks
- Captcha pages
- Repeated timeouts
- Empty or navigation-only content
- Competitor pages with strong anti-crawling controls

Each URL should try at most three levels:

```text
Level 1: httpx + trafilatura
Level 2: Playwright
Level 3: paid crawler API
```

If a level succeeds and passes the quality gate, the crawler should stop and should not upgrade to a more expensive method.

Every attempt should be written to `data/raw/fetch_attempts.jsonl`, including failed attempts.

### 7.5 Content Quality Gate

Every fetched page should receive a `content_quality_score` from `0.0` to `1.0`.

Mark content as low quality when:

- Main text is too short.
- Title is missing.
- Extracted text is mostly navigation, footer, cookie banner, or boilerplate.
- Text-to-HTML ratio is too low.
- The page contains captcha or blocked-access language.
- The HTTP status is `403`, `429`, or another blocking status.
- Extracted content is empty.

Recommended thresholds:

| Score | Meaning | Action |
|---:|---|---|
| `>= 0.7` | Good enough for the resource library | Store and continue |
| `0.4 - 0.69` | Partial content | Store, flag for review, and optionally retry with the next level |
| `< 0.4` | Failed or unreliable content | Upgrade to the next crawling level |

### 7.6 Paid Provider Recommendations

| Provider | Best For | Recommendation |
|---|---|---|
| Firecrawl | LLM-ready Markdown and webpage-to-resource-library extraction | Default paid fallback for this project |
| ScrapingBee | Simple API, JavaScript rendering, proxy fallback | Good first anti-blocking upgrade |
| Zyte | Strong anti-bot handling and Scrapy ecosystem fit | Best for harder competitor pages |
| Bright Data | Enterprise-scale scraping and difficult anti-bot targets | Use when scale and reliability matter more than cost |
| Apify | Scheduled cloud crawlers, Actors, and managed crawling workflows | Use when the crawler becomes a recurring production job |
| Browserless | Hosted Playwright or Puppeteer browser infrastructure | Use when Playwright works but local browser operations become hard to maintain |

Paid services should be configurable provider adapters, not hard-coded into the main crawler. The MVP should reserve the adapter interface but does not need paid API keys to run.

## 8. Chunking Rules

Chunk size:

- Chinese content: 300-800 Chinese characters per chunk.
- English content: 200-500 words per chunk.
- Keep FAQ pairs together.
- Keep tables or comparison sections together when possible.

Each chunk should ideally answer one concrete user question:

- What is this product?
- Who is it for?
- What problem does it solve?
- How much does it cost?
- How is it different from competitors?
- What are its limitations?
- What proof, case study, or result supports it?

Avoid chunks that mix unrelated topics.

## 9. Query Set

Store test queries in `data/eval/queries.csv`.

Recommended columns:

```csv
query_id,query,intent,priority,target_brand,notes
q001,What are the best tools for...,recommendation,high,Your Brand,Non-brand commercial query
q002,Your Brand vs Competitor A,comparison,high,Your Brand,Direct comparison query
q003,How much does ... cost,pricing,medium,Your Brand,Pricing intent
```

Recommended intent categories:

```text
recommendation
comparison
pricing
definition
problem_solution
alternative
how_to
review
use_case
```

## 10. Evaluation Design

### 10.1 Retrieval Evaluation

Input:

```text
query -> hybrid retrieval -> Top K chunks
```

Track:

- Whether our brand appears in Top 3.
- Whether our brand appears in Top 5.
- Whether our brand appears in Top 10.
- Which competitor appears above us.
- Which source type dominates the result.

Output file:

```text
data/eval/retrieval_results.csv
```

Suggested columns:

```csv
query_id,query,top_k,own_brand_rank,own_brand_in_top_3,own_brand_in_top_5,own_brand_in_top_10,winning_brand,winning_source_type,matched_urls
```

### 10.2 Generation Evaluation

Input:

```text
query -> retrieve Top K chunks -> LLM answer -> evaluate answer
```

Track:

- Does the answer mention our brand?
- Does the answer cite our URL?
- Does the answer recommend us?
- Does the answer recommend competitors instead?
- Does the answer use our unique claims or evidence?
- Does the answer hallucinate incorrect information?

Output file:

```text
data/eval/generation_results.csv
```

Suggested columns:

```csv
query_id,query,brand_mentioned,cited_own_url,recommended_own_brand,competitors_mentioned,answer_summary,issues
```

## 11. Core Metrics

| Metric | Meaning |
|---|---|
| Recall@3 | Our content appears in the top 3 retrieved chunks |
| Recall@5 | Our content appears in the top 5 retrieved chunks |
| Recall@10 | Our content appears in the top 10 retrieved chunks |
| Brand Mention Rate | Generated answers mention our brand |
| Citation Rate | Generated answers cite our URL |
| Recommendation Rate | Generated answers recommend our brand |
| Competitor Win Rate | Competitor content ranks or appears above us |
| Coverage Score | Our content answers the user's actual intent |

## 12. Optimization Loop

Run the same query set before and after content updates.

Recommended workflow:

```text
1. Build baseline index.
2. Run retrieval evaluation.
3. Run generation evaluation.
4. Identify weak queries and missing content.
5. Improve target pages.
6. Re-crawl updated pages.
7. Rebuild index.
8. Re-run the same evaluations.
9. Compare before vs after.
```

Example before/after report:

| Metric | Before | After |
|---|---:|---:|
| Recall@5 | 22% | 48% |
| Brand Mention Rate | 15% | 37% |
| Citation Rate | 8% | 26% |
| Competitor Win Rate | 71% | 43% |

## 13. Content Signals To Optimize

If retrieval or generation performance is weak, improve pages by adding:

- Clear definition sections.
- Product use cases.
- Target audience sections.
- FAQ blocks.
- Pricing or plan explanations.
- Comparison sections.
- Competitor alternative pages.
- Case studies.
- Industry terms and entity names.
- Evidence, metrics, screenshots, or examples.
- Limitations and "not suitable for" sections.

Good GEO content is not only persuasive. It must be extractable, factual, specific, and easy for a model to quote.

## 14. Implementation Milestones

### Milestone 1: Corpus Setup

Deliverables:

- `config/sources.yaml`
- `data/eval/queries.csv`
- Initial URL list for own site, competitors, and industry sources

Acceptance criteria:

- At least 20 own-site URLs.
- At least 50 competitor URLs.
- At least 50 non-brand queries.

### Milestone 2: Crawl And Clean

Deliverables:

- `data/raw/pages.jsonl`
- `data/raw/fetch_attempts.jsonl`
- `data/raw/crawl_logs.csv`
- `data/processed/documents.jsonl`
- `config/crawler.yaml`
- `scripts/score_content_quality.py`
- `scripts/paid_fetch_fallback.py`

Acceptance criteria:

- Level 1 crawler uses `httpx + trafilatura`.
- Playwright fallback is available for JavaScript-rendered or low-quality pages.
- Paid provider adapter is reserved, but MVP does not require paid API keys.
- Pages contain main content, not raw navigation noise.
- Each document has URL, title, brand, source type, and cleaned content.
- Failed crawls are logged with failure reason, status code, and fetch method.
- Each successful or failed attempt has a content quality score or explicit error type.
- URLs that require paid fallback are traceable as paid upgrade candidates.

### Milestone 3: Chunk And Index

Deliverables:

- `data/processed/chunks.jsonl`
- `vector_db/qdrant/`

Acceptance criteria:

- Each chunk has metadata.
- FAQ, pricing, and comparison content are preserved.
- Chunks can be searched by test queries.

### Milestone 4: Retrieval Evaluation

Deliverables:

- `data/eval/retrieval_results.csv`

Acceptance criteria:

- Each query produces Top 10 retrieved chunks.
- The system calculates Recall@3, Recall@5, and Recall@10.
- The report identifies competitor wins.

### Milestone 5: Generation Evaluation

Deliverables:

- `data/eval/generation_results.csv`

Acceptance criteria:

- Each query produces an LLM answer using retrieved chunks.
- The system records brand mention, citation, recommendation, and competitor mentions.
- Obvious hallucinations or incorrect claims are flagged.

### Milestone 6: GEO Report

Deliverables:

- `reports/geo_report.md`

Acceptance criteria:

- Report summarizes retrieval performance.
- Report summarizes generation performance.
- Report lists top weak queries.
- Report lists pages that should be optimized first.
- Report compares baseline vs updated results after content changes.

## 15. Suggested README Summary

Use this short description in the project README:

```markdown
# GEO Resource Library

This project builds a private retrieval and generation test environment for GEO optimization. It crawls our website, competitor websites, and industry sources, then evaluates whether our content is retrieved and cited by an LLM-style RAG system.

The goal is to measure whether content updates improve AI search visibility before waiting for public LLMs or search engines to crawl and surface the content.
```

## 16. Success Criteria

The MVP is successful when it can answer:

- Which target queries fail to retrieve our content?
- Which competitors outrank us in retrieval?
- Which pages are most often cited by the LLM?
- Which pages need GEO content improvements?
- Whether content updates improve Recall@5, Citation Rate, and Brand Mention Rate.

The project should not be considered a replacement for real-world monitoring. It is a fast local testing layer for GEO strategy and content iteration.
