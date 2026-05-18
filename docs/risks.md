# Risks

## Current Risks

- AlphaXXXX has a very small corpus footprint compared with leading competitors, which suppresses recall before answer generation can help.
- Full external API evaluation can export retrieved corpus excerpts; Codex tool execution is restricted, so the user must run that path locally.
- Current full API flow is still mostly stage-oriented; if interrupted, cache/run-state helps, but output files may not be streamed at ideal granularity.
- Parallel model runs need careful merging to avoid miscounting brand metrics or duplicating rows.
- Doubao Pro on OpenRouter may fail because the requested model id has previously returned errors.

## Architecture Drift Signals

- Crawler scripts gaining evaluator-specific logic.
- Evaluator scripts directly manipulating raw crawler outputs instead of processed contracts.
- New helper files that contain unrelated crawling, indexing, API, and reporting logic together.
- Report metrics being patched manually instead of tested through aggregation functions.

## Operational Risks

- Large raw page files are expensive to copy and should not be used as the primary downstream input when `documents.jsonl` or `chunks.jsonl` is enough.
- Paid fallback usage should remain traceable by URL, reason, provider, and quality score.
- API concurrency can increase rate limits, timeout, and partial-output risks unless retry/backoff and streaming writes are in place.
