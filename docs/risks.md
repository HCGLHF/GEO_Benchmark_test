# Risks

## Current Risks

- AlphaXXXX has a very small corpus footprint compared with leading competitors, which suppresses recall before answer generation can help.
- Full external API evaluation can export retrieved corpus excerpts; Codex tool execution is restricted, so the user must run that path locally.
- Current full API flow now streams scenario, rerank, and answer rows incrementally, but a single in-flight API call is still invisible until the call returns or fails.
- Resume support skips already-streamed scenario slots, rerank rows, and answer rows, but stale output files in a reused run directory can intentionally suppress reruns.
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
- API concurrency can increase rate limits, timeout, and partial-output risks; streaming writes reduce data loss but do not replace retry/backoff controls.
- Parallel full API runs should use per-model cache files to avoid SQLite lock contention and preserve model-level independence.
- For a fully fresh benchmark, use a new output directory or delete the old run directory outside Codex after confirming no results need to be preserved.
