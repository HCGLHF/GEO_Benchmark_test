# Project Context

## Goal

Build a GEO / AI search visibility resource library and evaluator for comparing AlphaXXXX against competitor and industry sites across retrieval, model answers, brand mentions, citations, and content coverage.

## User

The primary user is the AlphaXXXX project owner, who wants realistic GEO benchmarking, crawler-backed resource expansion, and actionable content strategy for improving AI recommendations.

## Core Concepts

- **Resource library**: crawled, cleaned, chunked, indexed website content used as the evaluation corpus.
- **GEO evaluation**: measuring whether AlphaXXXX is retrieved, mentioned, cited, and recommended by AI-search-like workflows.
- **Client acquisition simulator**: API-driven or local-safe simulation of potential customers asking for GEO / AI visibility help.
- **Crawling pipeline**: URL discovery, tiered fetch, content quality scoring, fallback handling, merge, clean, chunk, and indexing.
- **Full API run**: highest-fidelity evaluation path that sends retrieved evidence to external model APIs when run manually by the user.
- **Parallel full API run with watch**: one-command local orchestration that runs each model in an independent PowerShell worker, monitors progress with `watch_full_api_run.py`, and merges completed model runs.

## Non-Goals

- Do not build a general-purpose web search engine.
- Do not bypass login walls or authenticated content.
- Do not silently export local corpus excerpts to third-party APIs from Codex tool execution.
- Do not treat local deterministic simulation as equivalent to full external model realism.

## Constraints

- Keep `.env` local and never expose real API keys.
- Prefer local crawler paths before paid Firecrawl fallback.
- Preserve model independence: scenario generation, rerank, and answer evaluation must be tracked per model.
- Use `powershell -ExecutionPolicy Bypass -File .\scripts\run_full_api_parallel_with_watch.ps1 -QueriesPerModel 200` for high-fidelity multi-model runs when speed matters.
- Update `docs/next.md` after every development task.
- Before code changes, read `CONTEXT.md`, `docs/architecture.md`, `docs/risks.md`, `docs/next.md`, and ADRs in `docs/adr/`.
